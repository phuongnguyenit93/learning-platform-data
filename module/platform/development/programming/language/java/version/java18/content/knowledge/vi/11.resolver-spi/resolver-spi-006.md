# Lọc đúng họ địa chỉ và giữ thứ tự yêu cầu khi trả kết quả tra cứu thuận

> **Phạm vi:** Chương **Resolver SPI** của Java 18 (JEP 418). Bài tập trung vào hợp đồng `InetAddressResolver.lookupByName(host, policy)`: chỉ trả các họ IP được yêu cầu, sắp xếp nhóm IPv4/IPv6 theo `LookupPolicy` và giữ thứ tự ổn định trong từng nhóm. Các API trong bài vẫn được hỗ trợ trên JDK hiện đại; ví dụ dùng `java.net.spi` công khai, không dùng lớp nội bộ hoặc cơ chế legacy.

## 1. Hai yêu cầu độc lập của một lần tra cứu thuận

Một hostname có thể có nhiều địa chỉ, ví dụ máy chủ dual-stack:

~~~text
api.lab.invalid
  ├── IPv6: 2001:db8::10
  ├── IPv4: 192.0.2.10
  ├── IPv4: 192.0.2.11
  └── IPv6: 2001:db8::11
~~~

Khi gọi `InetAddress.getAllByName("api.lab.invalid")`, ứng dụng có thể nhận nhiều kết quả. Resolver phải tuân theo hai khía cạnh của `LookupPolicy`:

1. **Lọc họ địa chỉ:** caller yêu cầu IPv4, IPv6 hoặc cả hai.
2. **Thứ tự giữa các họ:** nếu có cả hai họ, caller có thể yêu cầu IPv4 trước, IPv6 trước hoặc thứ tự hệ thống.

Hai việc này phải được xử lý riêng. Cờ `IPV4` và `IPV6` quyết định địa chỉ nào được giữ lại; cờ `IPV4_FIRST` và `IPV6_FIRST` quyết định nhóm nào đứng trước khi kết quả có cả hai họ.

~~~text
lookupByName(host, policy)
          │
          ▼
Đọc policy.characteristics()
          │
          ├── IPV4 / IPV6: lọc họ địa chỉ
          │
          └── IPV4_FIRST / IPV6_FIRST: xếp thứ tự nhóm
          │
          ▼
Stream<InetAddress> theo thứ tự yêu cầu
~~~

Chữ ký phương thức trong `InetAddressResolver`:

~~~java
Stream<InetAddress> lookupByName(
        String host,
        InetAddressResolver.LookupPolicy lookupPolicy)
        throws UnknownHostException;
~~~

`lookupByName` trả về một `Stream<InetAddress>`. Resolver cần bảo đảm stream chứa địa chỉ phù hợp với hostname và policy, không trả địa chỉ thuộc họ bị caller loại trừ, đồng thời sắp xếp kết quả theo thứ tự yêu cầu.

## 2. Đọc policy trước khi xử lý kết quả

Bốn hằng số của `InetAddressResolver.LookupPolicy` là:

| Hằng số | Giá trị | Ý nghĩa |
|---|---:|---|
| `IPV4` | 1 | Cho phép trả địa chỉ IPv4. |
| `IPV6` | 2 | Cho phép trả địa chỉ IPv6. |
| `IPV4_FIRST` | 4 | Ưu tiên nhóm IPv4 đứng trước IPv6. |
| `IPV6_FIRST` | 8 | Ưu tiên nhóm IPv6 đứng trước IPv4. |

Đọc bitmask bằng phép AND (`&`):

~~~java
int flags = policy.characteristics();

boolean wantsIpv4 = (flags & LookupPolicy.IPV4) != 0;
boolean wantsIpv6 = (flags & LookupPolicy.IPV6) != 0;

boolean ipv4First = (flags & LookupPolicy.IPV4_FIRST) != 0;
boolean ipv6First = (flags & LookupPolicy.IPV6_FIRST) != 0;
~~~

Tạo policy bằng `LookupPolicy.of(...)`, kết hợp cờ bằng OR (`|`):

~~~java
// Chỉ IPv4
LookupPolicy ipv4Only = LookupPolicy.of(LookupPolicy.IPV4);

// Chỉ IPv6
LookupPolicy ipv6Only = LookupPolicy.of(LookupPolicy.IPV6);

// Cả hai, ưu tiên IPv4
LookupPolicy dualV4First = LookupPolicy.of(
        LookupPolicy.IPV4 | LookupPolicy.IPV6 | LookupPolicy.IPV4_FIRST);

// Cả hai, ưu tiên IPv6
LookupPolicy dualV6First = LookupPolicy.of(
        LookupPolicy.IPV4 | LookupPolicy.IPV6 | LookupPolicy.IPV6_FIRST);

// Cả hai, system order
LookupPolicy dualSystemOrder = LookupPolicy.of(
        LookupPolicy.IPV4 | LookupPolicy.IPV6);
~~~

Policy hợp lệ phải bật ít nhất một bit họ địa chỉ và không bật đồng thời hai bit `IPV4_FIRST`, `IPV6_FIRST`. `LookupPolicy.of(...)` ném `IllegalArgumentException` nếu vi phạm các điều kiện đó. Chi tiết cách tạo policy được trình bày trong bài về `LookupPolicy.of()`; ở đây ta tập trung vào cách resolver thực thi policy.

## 3. Lọc đúng họ IP

Không được chỉ kiểm tra xem danh sách có địa chỉ hay không rồi trả toàn bộ. Nếu caller yêu cầu IPv6, trả thêm IPv4 là vi phạm policy ngay cả khi IPv4 có thể kết nối được.

Dùng kiểu cụ thể của địa chỉ để nhận diện họ:

- `Inet4Address`: IPv4.
- `Inet6Address`: IPv6.

Ví dụ lọc:

~~~java
List<InetAddress> selected = new ArrayList<>();

for (InetAddress candidate : candidates) {
    if (candidate instanceof Inet4Address && wantsIpv4) {
        selected.add(candidate);
    } else if (candidate instanceof Inet6Address && wantsIpv6) {
        selected.add(candidate);
    }
}
~~~

Bảng kết quả mong đợi:

| Candidate ban đầu | Policy chỉ IPv4 | Policy chỉ IPv6 | Policy cả hai |
|---|---|---|---|
| `192.0.2.10` | Giữ | Loại | Giữ |
| `2001:db8::10` | Loại | Giữ | Giữ |
| `192.0.2.11` | Giữ | Loại | Giữ |
| `2001:db8::11` | Loại | Giữ | Giữ |

**Đừng suy luận họ IP từ chuỗi hiển thị.** Kiểu `InetAddress` đã cho biết địa chỉ là IPv4 hay IPv6. Cũng không nên coi mọi đối tượng không phải `Inet4Address` là IPv6; kiểm tra tường minh `Inet6Address` giúp nhánh xử lý rõ ràng và an toàn hơn.

Nếu sau bước lọc không còn địa chỉ nào phù hợp, resolver phải báo `UnknownHostException`. Không trả `Stream.empty()` để biểu diễn trường hợp không tìm được địa chỉ; điều đó làm sai hợp đồng lỗi của lookup.

~~~java
if (selected.isEmpty()) {
    throw new UnknownHostException(
            "No address matching lookup policy for " + host);
}
~~~

## 4. Giữ thứ tự yêu cầu bằng stable partition

Sau khi lọc, resolver cần xử lý thứ tự:

- `IPV4_FIRST`: tất cả IPv4 đứng trước tất cả IPv6.
- `IPV6_FIRST`: tất cả IPv6 đứng trước tất cả IPv4.
- Không có cờ `FIRST`: giữ system order.

Khi đổi thứ tự giữa các nhóm, nên **giữ thứ tự ban đầu bên trong từng nhóm**. Đây là stable partition: di chuyển cả nhóm IPv4 hoặc IPv6 mà không đảo các địa chỉ cùng họ.

Ví dụ đầu vào:

~~~text
Nguồn dữ liệu:
IPv6-A, IPv4-A, IPv4-B, IPv6-B
~~~

Kết quả theo policy:

| Policy | Kết quả |
|---|---|
| IPv4 only | IPv4-A, IPv4-B |
| IPv6 only | IPv6-A, IPv6-B |
| IPv4 và IPv6, `IPV4_FIRST` | IPv4-A, IPv4-B, IPv6-A, IPv6-B |
| IPv4 và IPv6, `IPV6_FIRST` | IPv6-A, IPv6-B, IPv4-A, IPv4-B |
| IPv4 và IPv6, không có cờ `FIRST` | IPv6-A, IPv4-A, IPv4-B, IPv6-B |

Có thể thực hiện bằng cách tạo hai danh sách theo họ rồi ghép lại:

~~~java
List<InetAddress> ipv4 = new ArrayList<>();
List<InetAddress> ipv6 = new ArrayList<>();

for (InetAddress candidate : candidates) {
    if (candidate instanceof Inet4Address && wantsIpv4) {
        ipv4.add(candidate);
    } else if (candidate instanceof Inet6Address && wantsIpv6) {
        ipv6.add(candidate);
    }
}

List<InetAddress> ordered = new ArrayList<>();

if (ipv4First) {
    ordered.addAll(ipv4);
    ordered.addAll(ipv6);
} else if (ipv6First) {
    ordered.addAll(ipv6);
    ordered.addAll(ipv4);
} else {
    // System order: lọc nhưng giữ nguyên thứ tự nguồn.
    for (InetAddress candidate : candidates) {
        if ((candidate instanceof Inet4Address && wantsIpv4)
                || (candidate instanceof Inet6Address && wantsIpv6)) {
            ordered.add(candidate);
        }
    }
}
~~~

Cách làm này giữ nguyên thứ tự trong từng nhóm vì vòng lặp duyệt nguồn theo thứ tự ban đầu. Khi không có bit `FIRST`, vòng lặp cuối cũng giữ nguyên thứ tự nguồn sau khi lọc.

Với resolver tích hợp, system order do nền tảng và cấu hình hệ thống quyết định. Với resolver tùy biến có nguồn dữ liệu riêng, hãy xác định rõ thứ tự nguồn được dùng làm system order cho implementation đó. Nếu cần ủy quyền phần tên không quản lý cho resolver tích hợp, gọi `configuration.builtinResolver().lookupByName(host, policy)`; không tự gọi ngược `InetAddress.getAllByName(host)` từ bên trong resolver vì có thể quay lại chính resolver đang chạy.

## 5. Ví dụ Java 18+: lọc và sắp xếp địa chỉ có thể kiểm chứng

Ví dụ dưới dùng hostname giả `dual.lab.invalid` và các địa chỉ thuộc dải dành cho tài liệu. Không cần DNS hoặc kết nối mạng. Nguồn dữ liệu cố ý đặt IPv6 trước để nhìn thấy sự khác nhau giữa system/source order, IPv4-first và IPv6-first.

Lưu thành `AddressOrderDemo.java`:

~~~java
import java.net.Inet4Address;
import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.UnknownHostException;
import java.net.spi.InetAddressResolver.LookupPolicy;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.stream.Stream;

public final class AddressOrderDemo {
    private static final String HOST = "dual.lab.invalid";

    private static InetAddress address(String host, int... octets) {
        if (octets.length != 4 && octets.length != 16) {
            throw new IllegalArgumentException("IPv4 needs 4 bytes; IPv6 needs 16");
        }

        byte[] raw = new byte[octets.length];
        for (int i = 0; i < octets.length; i++) {
            if (octets[i] < 0 || octets[i] > 255) {
                throw new IllegalArgumentException("Invalid IP octet");
            }
            raw[i] = (byte) octets[i];
        }

        try {
            // Tạo InetAddress từ byte, không thực hiện DNS lookup.
            return InetAddress.getByAddress(host, raw);
        } catch (UnknownHostException impossible) {
            throw new AssertionError(impossible);
        }
    }

    // Thứ tự nguồn được định nghĩa rõ trong ví dụ: IPv6, IPv4, IPv4, IPv6.
    private static final List<InetAddress> SOURCE_ORDER = List.of(
            address(HOST, 0x20, 0x01, 0x0d, 0xb8,
                    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x10),
            address(HOST, 192, 0, 2, 10),
            address(HOST, 192, 0, 2, 11),
            address(HOST, 0x20, 0x01, 0x0d, 0xb8,
                    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x11)
    );

    static Stream<InetAddress> lookupByName(
            String host, LookupPolicy policy) throws UnknownHostException {
        Objects.requireNonNull(host, "host");
        Objects.requireNonNull(policy, "policy");

        if (!HOST.equalsIgnoreCase(host)) {
            throw new UnknownHostException("Unknown host: " + host);
        }

        int flags = policy.characteristics();
        boolean wantsIpv4 = (flags & LookupPolicy.IPV4) != 0;
        boolean wantsIpv6 = (flags & LookupPolicy.IPV6) != 0;
        boolean ipv4First = (flags & LookupPolicy.IPV4_FIRST) != 0;
        boolean ipv6First = (flags & LookupPolicy.IPV6_FIRST) != 0;

        List<InetAddress> ipv4 = new ArrayList<>();
        List<InetAddress> ipv6 = new ArrayList<>();

        for (InetAddress candidate : SOURCE_ORDER) {
            if (candidate instanceof Inet4Address && wantsIpv4) {
                ipv4.add(candidate);
            } else if (candidate instanceof Inet6Address && wantsIpv6) {
                ipv6.add(candidate);
            }
        }

        List<InetAddress> result = new ArrayList<>();

        if (ipv4First) {
            result.addAll(ipv4);
            result.addAll(ipv6);
        } else if (ipv6First) {
            result.addAll(ipv6);
            result.addAll(ipv4);
        } else {
            // Không có bit FIRST: giữ thứ tự nguồn sau khi lọc.
            for (InetAddress candidate : SOURCE_ORDER) {
                if ((candidate instanceof Inet4Address && wantsIpv4)
                        || (candidate instanceof Inet6Address && wantsIpv6)) {
                    result.add(candidate);
                }
            }
        }

        if (result.isEmpty()) {
            throw new UnknownHostException(
                    "No address matching policy for " + host);
        }

        // List.stream() giữ encounter order của danh sách.
        return List.copyOf(result).stream();
    }

    private static void show(String label, LookupPolicy policy)
            throws UnknownHostException {
        try (Stream<InetAddress> addresses = lookupByName(HOST, policy)) {
            System.out.println(label + ": "
                    + addresses.map(InetAddress::getHostAddress).toList());
        }
    }

    public static void main(String[] args) throws Exception {
        show("IPv4 only",
                LookupPolicy.of(LookupPolicy.IPV4));

        show("IPv6 only",
                LookupPolicy.of(LookupPolicy.IPV6));

        show("System/source order",
                LookupPolicy.of(LookupPolicy.IPV4 | LookupPolicy.IPV6));

        show("IPv4 first",
                LookupPolicy.of(LookupPolicy.IPV4
                        | LookupPolicy.IPV6
                        | LookupPolicy.IPV4_FIRST));

        show("IPv6 first",
                LookupPolicy.of(LookupPolicy.IPV4
                        | LookupPolicy.IPV6
                        | LookupPolicy.IPV6_FIRST));
    }
}
~~~

Biên dịch và chạy bằng JDK 18 trở lên:

~~~shell
javac AddressOrderDemo.java
java AddressOrderDemo
~~~

Kết quả minh họa:

~~~text
IPv4 only: [192.0.2.10, 192.0.2.11]
IPv6 only: [2001:db8:0:0:0:0:0:10, 2001:db8:0:0:0:0:0:11]
System/source order: [2001:db8:0:0:0:0:0:10, 192.0.2.10, 192.0.2.11, 2001:db8:0:0:0:0:0:11]
IPv4 first: [192.0.2.10, 192.0.2.11, 2001:db8:0:0:0:0:0:10, 2001:db8:0:0:0:0:0:11]
IPv6 first: [2001:db8:0:0:0:0:0:10, 2001:db8:0:0:0:0:0:11, 192.0.2.10, 192.0.2.11]
~~~

Các điểm cần quan sát:

- IPv4-only không có địa chỉ IPv6.
- IPv6-only không có địa chỉ IPv4.
- Hai policy FIRST thay đổi vị trí của **nhóm** địa chỉ, không đảo thứ tự các phần tử trong nhóm.
- Không có FIRST thì kết quả giữ thứ tự nguồn của ví dụ sau khi lọc.

Đây là implementation minh họa trực tiếp thuật toán `lookupByName`; để `InetAddress` trong JVM sử dụng resolver này, cần đóng gói implementation trong một `InetAddressResolverProvider` và đăng ký service theo JEP 418. Ví dụ không tự thay đổi resolver toàn JVM.

## 6. Hợp đồng của Stream và xử lý trường hợp không có kết quả

Sau khi lọc và sắp xếp, resolver trả stream theo encounter order đã tạo. Một số điểm cần giữ:

- Stream không được là `null`.
- Không trả phần tử `null`.
- Không trả địa chỉ thuộc họ không được policy yêu cầu.
- Nếu không tìm thấy địa chỉ phù hợp, ném `UnknownHostException`.
- Không tiêu thụ stream rồi trả lại cùng stream đã dùng; stream chỉ được tiêu thụ một lần.
- Nếu cần bảo đảm snapshot ổn định, thu thập kết quả vào một danh sách riêng rồi trả `List.copyOf(result).stream()` như ví dụ.

Không dùng `parallelStream()` để xử lý rồi giả định mọi thao tác tiêu thụ sẽ giữ thứ tự. Nếu cần stream song song ở bước nội bộ, phải hiểu rõ đặc tính encounter order và dùng thao tác có bảo toàn thứ tự. Đối với danh sách địa chỉ thường nhỏ, xử lý tuần tự thường đơn giản và dễ kiểm chứng hơn.

Đối số `host` hoặc `policy` là `null` thì ném `NullPointerException`. Nếu hostname không tồn tại hoặc không có địa chỉ phù hợp với policy, ném `UnknownHostException`. Hai loại lỗi này không nên bị thay bằng `Stream.empty()` hoặc `null`.

## 7. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách đúng |
|---|---|---|
| Trả mọi candidate mà không lọc họ IP | Vi phạm yêu cầu IPv4-only hoặc IPv6-only. | Lọc theo `IPV4`/`IPV6` trước khi trả. |
| Sắp xếp trước rồi quên lọc | Kết quả vẫn có thể chứa họ IP bị cấm. | Xác định tập địa chỉ phù hợp trước. |
| Dùng `flags == LookupPolicy.IPV4` | Không nhận ra bit IPv4 khi mask có nhiều cờ. | Dùng `(flags & LookupPolicy.IPV4) != 0`. |
| Luôn ép IPv4 đứng trước | Làm sai policy IPv6-first hoặc system order. | Chỉ sắp xếp nhóm khi bit FIRST tương ứng được bật. |
| Đảo thứ tự toàn bộ danh sách | Các địa chỉ cùng họ cũng bị đảo ngoài yêu cầu. | Stable partition, giữ thứ tự trong mỗi nhóm. |
| Xem source order trong mọi môi trường là giống nhau | Kết quả system order có thể sai theo nền tảng. | Tôn trọng thứ tự hệ thống hoặc nguồn resolver thực tế. |
| Trả `Stream.empty()` khi không có IP phù hợp | Không báo lỗi lookup theo hợp đồng. | Ném `UnknownHostException`. |
| Gọi `InetAddress.getAllByName(host)` để fallback bên trong resolver | Có thể quay lại resolver hiện tại và gây đệ quy. | Dùng resolver tích hợp từ `Configuration.builtinResolver()`. |
| Tiêu thụ stream trước khi trả về | Caller nhận stream đã dùng và không thể đọc lại. | Tạo stream mới từ snapshot kết quả. |

## 8. Checklist kiểm chứng

| Ca kiểm thử | Kết quả cần xác minh |
|---|---|
| Policy chỉ `IPV4` | Mọi phần tử là `Inet4Address`. |
| Policy chỉ `IPV6` | Mọi phần tử là `Inet6Address`. |
| Cả hai họ, `IPV4_FIRST` | Tất cả IPv4 đứng trước IPv6. |
| Cả hai họ, `IPV6_FIRST` | Tất cả IPv6 đứng trước IPv4. |
| Cả hai họ, không có FIRST | Giữ system/source order. |
| Nhiều địa chỉ cùng họ | Giữ thứ tự của nguồn trong nhóm. |
| Không có địa chỉ phù hợp | Ném `UnknownHostException`. |
| `host == null` | Ném `NullPointerException`. |
| `policy == null` | Ném `NullPointerException`. |
| Hostname không được quản lý | Ủy quyền đúng resolver tích hợp nếu thiết kế có fallback. |

Khi kiểm thử, hãy dùng ít nhất một hostname có cả IPv4 và IPv6, một hostname chỉ có một họ và một hostname không có địa chỉ. Kiểm tra cả **tập phần tử** lẫn **thứ tự**; chỉ so sánh số lượng kết quả không chứng minh resolver tuân thủ policy.

## 9. Câu hỏi tự đánh giá

1. Vì sao lọc họ IP và sắp xếp thứ tự phải là hai bước riêng?
2. Nếu policy chỉ có `IPV6`, resolver có được trả thêm IPv4 khi IPv6 không kết nối được không?
3. `IPV4_FIRST` yêu cầu sắp xếp những gì? Nó có cho phép đảo thứ tự các địa chỉ IPv4 cùng nhóm không?
4. Khi không có bit FIRST, resolver cần tôn trọng thứ tự nào?
5. Vì sao trả `Stream.empty()` không tương đương với ném `UnknownHostException`?
6. Tại sao không nên gọi `InetAddress.getAllByName(host)` từ chính `lookupByName` để fallback?

**Ghi nhớ:** Trước hết lọc theo `IPV4` và `IPV6`; tiếp theo sắp xếp nhóm theo `IPV4_FIRST` hoặc `IPV6_FIRST`; nếu không có cờ FIRST thì giữ system order. Stable partition giúp ưu tiên đúng họ địa chỉ mà vẫn bảo toàn thứ tự các địa chỉ trong từng nhóm. Trả stream không rỗng theo encounter order hoặc ném `UnknownHostException` khi không có địa chỉ phù hợp.

## Tài liệu tham khảo chính thức

- [OpenJDK JEP 418 – Internet-Address Resolution SPI](https://openjdk.org/jeps/418).
- [Java SE 26: `InetAddressResolver` – hợp đồng `lookupByName`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/spi/InetAddressResolver.html).
- [Java SE 26: `InetAddressResolver.LookupPolicy` – các cờ họ địa chỉ và thứ tự](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/spi/InetAddressResolver.LookupPolicy.html).
- [Java SE 26: `InetAddressResolverProvider.Configuration` – resolver tích hợp](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/spi/InetAddressResolverProvider.Configuration.html).
