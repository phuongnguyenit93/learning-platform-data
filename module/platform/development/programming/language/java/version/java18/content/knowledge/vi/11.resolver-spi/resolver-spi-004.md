# `LookupPolicy.characteristics()`: đọc bitmask yêu cầu họ địa chỉ và thứ tự kết quả

> **Phạm vi:** Chương **Resolver SPI** của Java 18 (JEP 418). `InetAddressResolver.LookupPolicy` vẫn là API công khai trên JDK hiện đại để mô tả những họ địa chỉ được yêu cầu và thứ tự kết quả của forward lookup. Bài tập trung vào `characteristics()`, cách đọc từng bit, cách kết hợp cờ và cách resolver áp dụng policy trong `lookupByName`. Các ví dụ dùng API công khai, không phụ thuộc lớp nội bộ của JDK.

## 1. Vai trò của `LookupPolicy` trong Resolver SPI

Khi ứng dụng yêu cầu phân giải một hostname, kết quả có thể gồm nhiều địa chỉ:

- IPv4, ví dụ `192.0.2.10`.
- IPv6, ví dụ `2001:db8::10`.
- Nhiều địa chỉ thuộc cùng một họ IP, tùy nguồn dữ liệu và cấu hình mạng.

Không phải caller nào cũng muốn cả hai họ địa chỉ hoặc cùng một thứ tự. Một ứng dụng có thể chỉ hỗ trợ IPv4; một ứng dụng khác có thể hỗ trợ song song IPv4/IPv6 nhưng ưu tiên IPv6.

JEP 418 đưa ra `InetAddressResolver.LookupPolicy` để biểu đạt yêu cầu đó. JDK truyền policy vào phương thức:

~~~java
Stream<InetAddress> lookupByName(
        String host,
        InetAddressResolver.LookupPolicy lookupPolicy)
        throws UnknownHostException;
~~~

`LookupPolicy` mô tả hai khía cạnh:

1. **Họ địa chỉ cần truy vấn:** IPv4, IPv6 hoặc cả hai.
2. **Thứ tự giữa hai họ:** IPv4 trước, IPv6 trước hoặc thứ tự hệ thống.

Sơ đồ luồng xử lý:

~~~text
Caller
  │
  │ InetAddress.getAllByName("api.example.test")
  ▼
InetAddressResolver.lookupByName(host, policy)
  │
  ├── policy.characteristics()
  │       │
  │       ├── các bit IPV4 / IPV6
  │       └── các bit IPV4_FIRST / IPV6_FIRST
  │
  ▼
Resolver lọc họ IP và sắp xếp theo policy
  │
  ▼
Stream<InetAddress>
~~~

`LookupPolicy.characteristics()` trả về tập cờ dưới dạng `int`. Đây là cách đọc yêu cầu của caller; phương thức không tự truy vấn DNS, không tạo địa chỉ và cũng không thay đổi policy.

## 2. Bốn bit đặc trưng và giá trị của chúng

JDK công khai bốn hằng số `int` trong `InetAddressResolver.LookupPolicy`:

| Hằng số | Giá trị thập phân | Dạng nhị phân 4 bit | Ý nghĩa |
|---|---:|---|---|
| `IPV4` | 1 | `0001` | Yêu cầu truy vấn địa chỉ IPv4. |
| `IPV6` | 2 | `0010` | Yêu cầu truy vấn địa chỉ IPv6. |
| `IPV4_FIRST` | 4 | `0100` | Trả các địa chỉ IPv4 trước IPv6. |
| `IPV6_FIRST` | 8 | `1000` | Trả các địa chỉ IPv6 trước IPv4. |

Các bit là những cờ độc lập nên có thể kết hợp bằng toán tử OR theo bit (`|`). Ví dụ:

~~~java
int characteristics =
        LookupPolicy.IPV4 | LookupPolicy.IPV6 | LookupPolicy.IPV6_FIRST;

LookupPolicy policy = LookupPolicy.of(characteristics);
~~~

Giá trị tổng hợp là `11` (nhị phân `1011`):

~~~text
IPV4          0001
IPV6          0010
IPV6_FIRST    1000
              ----
OR            1011  = 11
~~~

Không nên ghi trực tiếp các số `1`, `2`, `4`, `8` trong mã ứng dụng. Hãy dùng tên hằng số để thể hiện ý nghĩa và tránh phụ thuộc vào các con số khó đọc.

## 3. Đọc từng bit bằng `characteristics()`

Đoạn mã cốt lõi:

~~~java
int flags = lookupPolicy.characteristics();

boolean wantsIpv4 =
        (flags & LookupPolicy.IPV4) != 0;

boolean wantsIpv6 =
        (flags & LookupPolicy.IPV6) != 0;

boolean ipv4First =
        (flags & LookupPolicy.IPV4_FIRST) != 0;

boolean ipv6First =
        (flags & LookupPolicy.IPV6_FIRST) != 0;
~~~

Toán tử AND theo bit (`&`) giữ lại những bit có mặt ở cả hai toán hạng. Nếu kết quả khác 0, cờ đang được bật.

Ví dụ policy yêu cầu cả hai họ và ưu tiên IPv6:

~~~java
LookupPolicy policy = LookupPolicy.of(
        LookupPolicy.IPV4
                | LookupPolicy.IPV6
                | LookupPolicy.IPV6_FIRST);

int flags = policy.characteristics();

System.out.println((flags & LookupPolicy.IPV4) != 0);       // true
System.out.println((flags & LookupPolicy.IPV6) != 0);       // true
System.out.println((flags & LookupPolicy.IPV4_FIRST) != 0); // false
System.out.println((flags & LookupPolicy.IPV6_FIRST) != 0); // true
~~~

**Không so sánh toàn bộ giá trị bằng `==` để kiểm tra một cờ.** Ví dụ, policy chứa cả `IPV4` và `IPV6` có giá trị `3`, do đó `flags == LookupPolicy.IPV4` là false dù bit IPv4 đang bật. Cách kiểm tra đúng là `(flags & LookupPolicy.IPV4) != 0`.

Có thể đọc tất cả các cờ một lần rồi dùng chúng trong quá trình lọc/sắp xếp. Không cần gọi `characteristics()` nhiều lần cho cùng một thao tác.

## 4. Kết hợp bitmask: những policy hợp lệ

Bảng dưới cho thấy các tổ hợp thường dùng. Cột “Giá trị” giúp quan sát cách OR hoạt động; trong mã thực tế vẫn nên dùng hằng số.

| Yêu cầu | Biểu thức | Giá trị |
|---|---|---:|
| Chỉ IPv4 | `IPV4` | 1 |
| Chỉ IPv6 | `IPV6` | 2 |
| Cả hai, thứ tự hệ thống | `IPV4 | IPV6` | 3 |
| Cả hai, IPv4 trước | `IPV4 | IPV6 | IPV4_FIRST` | 7 |
| Cả hai, IPv6 trước | `IPV4 | IPV6 | IPV6_FIRST` | 11 |
| Chỉ IPv4, đồng thời đặt cờ IPv4 trước | `IPV4 | IPV4_FIRST` | 5 |

### Điều kiện hợp lệ khi gọi `LookupPolicy.of(int)`

`LookupPolicy.of(int characteristics)` là factory method tạo policy. Javadoc quy định:

- Phải có ít nhất một trong hai bit `IPV4` hoặc `IPV6`. Nếu không có bit họ địa chỉ nào, policy không hợp lệ.
- Không được bật đồng thời `IPV4_FIRST` và `IPV6_FIRST`. Hai yêu cầu thứ tự này mâu thuẫn.
- Nếu không bật cờ thứ tự nào, thứ tự kết quả là **system order**.
- Nếu bitmask không hợp lệ, factory ném `IllegalArgumentException`.

Ví dụ hợp lệ:

~~~java
LookupPolicy ipv4Only =
        LookupPolicy.of(LookupPolicy.IPV4);

LookupPolicy ipv6Only =
        LookupPolicy.of(LookupPolicy.IPV6);

LookupPolicy dualStack =
        LookupPolicy.of(LookupPolicy.IPV4 | LookupPolicy.IPV6);

LookupPolicy dualStackV4First =
        LookupPolicy.of(LookupPolicy.IPV4
                | LookupPolicy.IPV6
                | LookupPolicy.IPV4_FIRST);
~~~

Ví dụ không hợp lệ:

~~~java
// Không yêu cầu họ địa chỉ nào.
LookupPolicy.of(0);

// Không thể yêu cầu cả hai thứ tự cùng lúc.
LookupPolicy.of(LookupPolicy.IPV4
        | LookupPolicy.IPV6
        | LookupPolicy.IPV4_FIRST
        | LookupPolicy.IPV6_FIRST);
~~~

Cả hai lời gọi trên ném `IllegalArgumentException`. Việc kiểm tra nên giao cho factory chính thức thay vì tự xây một policy giả hoặc truyền số bitmask tự chế.

Một cờ thứ tự khi chỉ có một họ IP được yêu cầu không tạo ra thứ tự giữa hai họ vì kết quả không chứa họ còn lại. Tuy vậy, để mã dễ đọc, nên chỉ đặt cờ thứ tự khi thực sự cần biểu đạt ưu tiên.

## 5. “System order” có nghĩa gì?

Nếu cả `IPV4_FIRST` và `IPV6_FIRST` đều không được bật, policy yêu cầu thứ tự hệ thống. Resolver không nên tự áp đặt một ưu tiên IPv4/IPv6 trái với thứ tự đó.

Với resolver tích hợp của nền tảng, thứ tự mặc định được xây dựng dựa trên các system properties liên quan đến cách trả về địa chỉ IPv4/IPv6. Một property quan trọng là:

`java.net.preferIPv6Addresses`

Theo tài liệu networking properties của JDK hiện đại:

| Giá trị | Ý nghĩa |
|---|---|
| `false` (mặc định) | Ưu tiên IPv4 khi hostname có cả IPv4 và IPv6. |
| `true` | Ưu tiên IPv6 khi có thể. |
| `system` | Giữ thứ tự địa chỉ do resolver toàn hệ thống trả về. |

Property này được kiểm tra khi JVM khởi động. Nếu cần thay đổi hành vi mặc định, cấu hình qua tham số lúc chạy, ví dụ:

~~~shell
java -Djava.net.preferIPv6Addresses=true -jar app.jar
~~~

Lưu ý:

- Đây là cấu hình mặc định của nền tảng; không phải cách sửa một đối tượng `LookupPolicy` đã được tạo.
- Một resolver tùy biến vẫn phải đọc và thực hiện policy được truyền vào `lookupByName`.
- Không giả định mọi môi trường có cùng thứ tự khi dùng system order; kết quả còn phụ thuộc hệ điều hành và resolver nền tảng.
- Không nhầm `java.net.preferIPv6Addresses` với cấu hình chọn loại socket. Hai mục tiêu cấu hình mạng khác nhau.

## 6. Áp dụng bitmask trong `lookupByName`

Resolver phải dùng các bit họ địa chỉ để lọc kết quả, sau đó áp dụng bit thứ tự. Chỉ đọc policy mà không dùng nó sẽ làm sai hợp đồng của SPI.

Ví dụ dưới đây dùng hostname giả lập `dual.lab.invalid` với hai địa chỉ IPv4 và một địa chỉ IPv6 thuộc dải dành cho tài liệu. Dữ liệu được tạo từ byte bằng `InetAddress.getByAddress`, không truy vấn DNS bên ngoài.

Lưu thành `LookupPolicyDemo.java`:

~~~java
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.UnknownHostException;
import java.net.spi.InetAddressResolver.LookupPolicy;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.stream.Stream;

public class LookupPolicyDemo {
    private static final String HOST = "dual.lab.invalid";

    private static InetAddress address(String host, int... octets) {
        byte[] bytes = new byte[octets.length];
        for (int i = 0; i < octets.length; i++) {
            if (octets[i] < 0 || octets[i] > 255) {
                throw new IllegalArgumentException("Invalid IP octet");
            }
            bytes[i] = (byte) octets[i];
        }
        try {
            return InetAddress.getByAddress(host, bytes);
        } catch (UnknownHostException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    // Cố ý đặt IPv6 trước trong nguồn để nhìn thấy tác dụng của policy.
    private static final List<InetAddress> CANDIDATES = List.of(
            address(HOST, 0x20, 0x01, 0x0d, 0xb8,
                    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x10),
            address(HOST, 192, 0, 2, 10),
            address(HOST, 192, 0, 2, 11)
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

        // Bước 1: lọc các địa chỉ theo họ được yêu cầu.
        List<InetAddress> selected = new ArrayList<>();
        for (InetAddress candidate : CANDIDATES) {
            boolean isIpv4 = candidate instanceof Inet4Address;
            boolean isIpv6 = !isIpv4; // dữ liệu demo chỉ có Inet4/Inet6

            if ((isIpv4 && wantsIpv4) || (isIpv6 && wantsIpv6)) {
                selected.add(candidate);
            }
        }

        if (selected.isEmpty()) {
            throw new UnknownHostException(
                    "No address matching policy for " + host);
        }

        // Bước 2: sắp xếp ổn định theo họ nếu caller yêu cầu.
        if (ipv4First) {
            selected.sort(Comparator.comparingInt(
                    (InetAddress ip) -> ip instanceof Inet4Address ? 0 : 1));
        } else if (ipv6First) {
            selected.sort(Comparator.comparingInt(
                    (InetAddress ip) -> ip instanceof Inet4Address ? 1 : 0));
        }
        // Không có bit FIRST: giữ nguyên system/source order.

        return selected.stream();
    }

    private static void run(String label, LookupPolicy policy)
            throws UnknownHostException {
        int flags = policy.characteristics();
        String binary = String.format("%4s",
                Integer.toBinaryString(flags)).replace(' ', '0');

        try (Stream<InetAddress> result = lookupByName(HOST, policy)) {
            System.out.println(label + " | mask=" + flags
                    + " (0b" + binary + ") | "
                    + result.map(InetAddress::getHostAddress).toList());
        }
    }

    public static void main(String[] args) throws Exception {
        run("IPv4 only",
                LookupPolicy.of(LookupPolicy.IPV4));

        run("IPv6 only",
                LookupPolicy.of(LookupPolicy.IPV6));

        run("System order",
                LookupPolicy.of(LookupPolicy.IPV4 | LookupPolicy.IPV6));

        run("IPv4 first",
                LookupPolicy.of(LookupPolicy.IPV4
                        | LookupPolicy.IPV6
                        | LookupPolicy.IPV4_FIRST));

        run("IPv6 first",
                LookupPolicy.of(LookupPolicy.IPV4
                        | LookupPolicy.IPV6
                        | LookupPolicy.IPV6_FIRST));
    }
}
~~~

Biên dịch và chạy bằng JDK 18 trở lên:

~~~shell
javac LookupPolicyDemo.java
java LookupPolicyDemo
~~~

Kết quả có dạng:

~~~text
IPv4 only | mask=1 (0b0001) | [192.0.2.10, 192.0.2.11]
IPv6 only | mask=2 (0b0010) | [2001:db8:0:0:0:0:0:10]
System order | mask=3 (0b0011) | [2001:db8:0:0:0:0:0:10, 192.0.2.10, 192.0.2.11]
IPv4 first | mask=7 (0b0111) | [192.0.2.10, 192.0.2.11, 2001:db8:0:0:0:0:0:10]
IPv6 first | mask=11 (0b1011) | [2001:db8:0:0:0:0:0:10, 192.0.2.10, 192.0.2.11]
~~~

Ví dụ minh họa ba việc khác nhau:

1. `IPV4`/`IPV6` quyết định **địa chỉ nào được giữ lại**.
2. `IPV4_FIRST`/`IPV6_FIRST` quyết định **nhóm nào đứng trước** khi có cả hai họ.
3. Khi không có cờ `FIRST`, thứ tự nguồn được giữ nguyên. Trong ví dụ, nguồn cố ý đặt IPv6 trước để làm rõ hành vi này.

Đây là hàm minh họa hợp đồng lọc và sắp xếp, không phải một provider đã được đăng ký vào JVM. Để `InetAddress` sử dụng resolver tùy biến, implementation cần được cung cấp qua `InetAddressResolverProvider` và cơ chế `ServiceLoader`/JPMS theo JEP 418.

## 7. Các lỗi thường gặp khi đọc và xử lý bitmask

| Lỗi | Vì sao sai | Cách đúng |
|---|---|---|
| Dùng `flags == IPV4` để kiểm tra IPv4 | Bitmask có thể đồng thời chứa nhiều cờ. | Dùng `(flags & IPV4) != 0`. |
| Dùng `&&` để ghép hai hằng số | `&&` là toán tử logic, không kết hợp bit. | Dùng `|`. |
| Dùng `||` thay cho OR bit | Biểu thức cho kết quả boolean, không phải bitmask. | Dùng `|`. |
| Bỏ qua cờ họ IP và chỉ sắp xếp | Có thể trả IPv4/IPv6 mà caller không yêu cầu. | Lọc trước, sắp xếp sau. |
| Bật cả `IPV4_FIRST` và `IPV6_FIRST` | Hai yêu cầu thứ tự xung đột. | Chọn một hoặc không chọn cờ nào. |
| Không bật `IPV4` lẫn `IPV6` | Không có họ địa chỉ để truy vấn. | Bật ít nhất một cờ họ IP. |
| Mặc định ép IPv4 trước khi không có cờ FIRST | Làm sai yêu cầu system order. | Giữ thứ tự hệ thống/nguồn. |
| Ghi số bitmask trực tiếp trong mã | Khó đọc và dễ nhầm cờ. | Dùng các hằng số công khai. |
| Nghĩ `characteristics()` tự thay đổi cấu hình mạng | Phương thức chỉ trả về giá trị của policy. | Cấu hình policy lúc tạo và thực hiện nó trong resolver. |

## 8. Checklist kiểm chứng

| Trường hợp | Điều cần xác minh |
|---|---|
| `LookupPolicy.of(IPV4)` | Chỉ giữ địa chỉ IPv4. |
| `LookupPolicy.of(IPV6)` | Chỉ giữ địa chỉ IPv6. |
| `IPV4 | IPV6` | Giữ cả hai họ. |
| `IPV4_FIRST` | IPv4 đứng trước IPv6 nếu cả hai họ có kết quả. |
| `IPV6_FIRST` | IPv6 đứng trước IPv4 nếu cả hai họ có kết quả. |
| Không có bit FIRST | Không tự áp đặt thứ tự ưu tiên. |
| `LookupPolicy.of(0)` | Ném `IllegalArgumentException`. |
| Cả hai bit FIRST | Ném `IllegalArgumentException`. |
| Hostname không có địa chỉ phù hợp | Resolver ném `UnknownHostException`. |
| Policy là `null` | `lookupByName` ném `NullPointerException`. |

Khi kiểm thử resolver thực tế, nên có hostname chỉ có IPv4, chỉ có IPv6, có cả hai và không có bản ghi phù hợp. Đừng chỉ kiểm tra một hostname dual-stack vì như vậy chưa chứng minh được resolver đã lọc đúng họ IP.

## 9. Câu hỏi tự đánh giá

1. Vì sao `(flags & LookupPolicy.IPV4) != 0` đúng hơn `flags == LookupPolicy.IPV4`?
2. Giá trị bitmask nào biểu diễn cả IPv4 và IPv6, ưu tiên IPv6? Hãy viết biểu thức bằng hằng số.
3. Nếu không có `IPV4_FIRST` và `IPV6_FIRST`, resolver phải hiểu thứ tự kết quả ra sao?
4. Vì sao một policy có cả hai bit thứ tự bị xem là không hợp lệ?
5. `characteristics()` có thực hiện DNS lookup hay thay đổi policy không?
6. Nếu caller chỉ yêu cầu IPv6 nhưng resolver trả cả IPv4 và IPv6, hợp đồng nào đã bị vi phạm?

**Ghi nhớ:** `characteristics()` trả về một `int` bitmask. Dùng `&` để đọc từng cờ, dùng `|` để kết hợp yêu cầu, lọc theo `IPV4`/`IPV6` rồi mới áp dụng thứ tự `IPV4_FIRST`/`IPV6_FIRST`. Nếu không có cờ thứ tự, tôn trọng system order. Đây là hợp đồng API công khai từ Java 18 vẫn còn áp dụng trên JDK hiện đại.

## Tài liệu tham khảo chính thức

- [OpenJDK JEP 418 – Internet-Address Resolution SPI](https://openjdk.org/jeps/418).
- [Java SE 26: `InetAddressResolver.LookupPolicy` – `characteristics()` và `of(int)`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/spi/InetAddressResolver.LookupPolicy.html).
- [Java SE 26: `InetAddressResolver` – hợp đồng `lookupByName`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/spi/InetAddressResolver.html).
- [Java SE 26: Constant Field Values – các bit của `LookupPolicy`](https://docs.oracle.com/en/java/javase/26/docs/api/constant-values.html).
- [Java SE 26: Networking Properties – `java.net.preferIPv6Addresses`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/doc-files/net-properties.html).
