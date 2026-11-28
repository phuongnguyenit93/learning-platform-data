# `LookupPolicy.of()`: tổ hợp `IPV4`, `IPV6`, `IPV4_FIRST` và `IPV6_FIRST` hợp lệ

> **Phạm vi:** Bài thuộc chương **Resolver SPI** của Java 18 (JEP 418). `InetAddressResolver.LookupPolicy` vẫn là API công khai trên JDK hiện đại để mô tả họ địa chỉ và thứ tự trả kết quả trong forward lookup. Trọng tâm là factory `LookupPolicy.of(int)`, bốn bit đặc trưng, các tổ hợp hợp lệ/không hợp lệ và cách kiểm chứng bằng Java. Chỉ sử dụng API được hỗ trợ hiện nay, không dựa vào lớp nội bộ hoặc cơ chế legacy.

## 1. Vì sao cần tạo `LookupPolicy`?

Một hostname có thể phân giải thành nhiều địa chỉ. Ví dụ, một máy chủ dual-stack có cả IPv4 và IPv6:

~~~text
api.example.test
   ├── IPv4: 192.0.2.40
   ├── IPv4: 192.0.2.41
   └── IPv6: 2001:db8::40
~~~

Caller có thể cần một trong các yêu cầu:

- Chỉ truy vấn địa chỉ IPv4.
- Chỉ truy vấn địa chỉ IPv6.
- Truy vấn cả hai họ và ưu tiên IPv4.
- Truy vấn cả hai họ và ưu tiên IPv6.
- Truy vấn cả hai họ, để thứ tự theo hệ thống.

JEP 418 cung cấp `InetAddressResolver.LookupPolicy` để biểu đạt các yêu cầu đó. Một đối tượng policy được truyền vào phương thức:

~~~java
Stream<InetAddress> lookupByName(
        String host,
        InetAddressResolver.LookupPolicy lookupPolicy)
        throws UnknownHostException;
~~~

Factory `LookupPolicy.of(int characteristics)` tạo đối tượng policy từ một bitmask. Phương thức này chỉ **tạo và kiểm tra cấu hình yêu cầu**; nó không thực hiện DNS lookup, không kết nối mạng và không tự lọc địa chỉ.

## 2. Bốn hằng số bitmask

`InetAddressResolver.LookupPolicy` công khai bốn hằng số kiểu `int`:

| Hằng số | Giá trị | Bit nhị phân | Ý nghĩa |
|---|---:|---|---|
| `IPV4` | 1 | `0001` | Yêu cầu truy vấn địa chỉ IPv4. |
| `IPV6` | 2 | `0010` | Yêu cầu truy vấn địa chỉ IPv6. |
| `IPV4_FIRST` | 4 | `0100` | Yêu cầu resolver trả IPv4 trước IPv6. |
| `IPV6_FIRST` | 8 | `1000` | Yêu cầu resolver trả IPv6 trước IPv4. |

Các bit có thể kết hợp bằng phép OR theo bit (`|`). Ví dụ, yêu cầu cả IPv4 lẫn IPv6, ưu tiên IPv6:

~~~java
import java.net.spi.InetAddressResolver.LookupPolicy;

LookupPolicy policy = LookupPolicy.of(
        LookupPolicy.IPV4
                | LookupPolicy.IPV6
                | LookupPolicy.IPV6_FIRST);
~~~

Phép OR tạo mask `1011` (thập phân `11`):

~~~text
IPV4          0001
IPV6          0010
IPV6_FIRST    1000
              ----
OR            1011 = 11
~~~

Trong mã ứng dụng, hãy dùng tên hằng số thay vì ghi trực tiếp các số `1`, `2`, `4`, `8`. Tên hằng số làm rõ mục đích và giảm lỗi khi ghép bit.

## 3. Quy tắc để `LookupPolicy.of(int)` chấp nhận mask

Javadoc quy định hai điều kiện chính đối với `characteristics`:

1. Phải bật ít nhất một trong hai bit họ địa chỉ: `IPV4` hoặc `IPV6`.
2. Không được bật đồng thời `IPV4_FIRST` và `IPV6_FIRST`.

Nếu vi phạm một trong hai điều kiện, `LookupPolicy.of(...)` ném `IllegalArgumentException`.

### 3.1. Chọn họ địa chỉ

Có ba lựa chọn hợp lệ cho hai bit họ địa chỉ:

| Bit họ địa chỉ | Mask | Yêu cầu |
|---|---:|---|
| `IPV4` | 1 | Chỉ IPv4. |
| `IPV6` | 2 | Chỉ IPv6. |
| `IPV4 | IPV6` | 3 | Cả IPv4 và IPv6. |

Mask `0` không hợp lệ vì caller chưa yêu cầu họ địa chỉ nào:

~~~java
LookupPolicy.of(0); // IllegalArgumentException
~~~

Chỉ bật một bit thứ tự mà không bật bit họ địa chỉ cũng không hợp lệ:

~~~java
LookupPolicy.of(LookupPolicy.IPV4_FIRST); // IllegalArgumentException
LookupPolicy.of(LookupPolicy.IPV6_FIRST); // IllegalArgumentException
~~~

### 3.2. Chọn thứ tự kết quả

Có ba lựa chọn cho bit thứ tự:

| Bit thứ tự | Mask | Yêu cầu |
|---|---:|---|
| Không có bit FIRST | 0 | System order. |
| `IPV4_FIRST` | 4 | IPv4 đứng trước IPv6. |
| `IPV6_FIRST` | 8 | IPv6 đứng trước IPv4. |

Không được bật cả hai bit FIRST vì hai yêu cầu thứ tự xung đột:

~~~java
LookupPolicy.of(
        LookupPolicy.IPV4
                | LookupPolicy.IPV6
                | LookupPolicy.IPV4_FIRST
                | LookupPolicy.IPV6_FIRST); // IllegalArgumentException
~~~

Nếu không có bit FIRST, policy yêu cầu **system order**. Resolver cần tôn trọng thứ tự hệ thống mà nó sử dụng, thay vì tự áp đặt IPv4-first hoặc IPv6-first.

### 3.3. Có chín tổ hợp hợp lệ

Kết hợp ba lựa chọn họ địa chỉ với ba lựa chọn thứ tự tạo ra chín tổ hợp:

| Họ địa chỉ | System order | IPv4 first | IPv6 first |
|---|---:|---:|---:|
| Chỉ IPv4 | 1 | 5 | 9 |
| Chỉ IPv6 | 2 | 6 | 10 |
| IPv4 và IPv6 | 3 | 7 | 11 |

Các mask trong bảng được tạo như sau:

~~~java
int ipv4System = LookupPolicy.IPV4;
int ipv4First = LookupPolicy.IPV4 | LookupPolicy.IPV4_FIRST;
int ipv4Ipv6First = LookupPolicy.IPV4 | LookupPolicy.IPV6_FIRST;

int ipv6System = LookupPolicy.IPV6;
int ipv6Ipv4First = LookupPolicy.IPV6 | LookupPolicy.IPV4_FIRST;
int ipv6First = LookupPolicy.IPV6 | LookupPolicy.IPV6_FIRST;

int dualSystem = LookupPolicy.IPV4 | LookupPolicy.IPV6;
int dualIpv4First = dualSystem | LookupPolicy.IPV4_FIRST;
int dualIpv6First = dualSystem | LookupPolicy.IPV6_FIRST;
~~~

Khi chỉ yêu cầu một họ địa chỉ, cờ FIRST không tạo ra khác biệt về thứ tự giữa hai họ vì kết quả không có họ còn lại. Những mask đó vẫn đáp ứng hai điều kiện hợp lệ của Javadoc; trong mã ứng dụng, thường nên chọn system order cho trường hợp một họ để biểu đạt ý định rõ ràng.

## 4. Những mask không hợp lệ

Các nhóm dưới đây đều dẫn đến `IllegalArgumentException`:

| Mask | Vì sao không hợp lệ |
|---:|---|
| 0 | Không bật `IPV4` hoặc `IPV6`. |
| 4 | Chỉ có `IPV4_FIRST`, không có họ địa chỉ. |
| 8 | Chỉ có `IPV6_FIRST`, không có họ địa chỉ. |
| 12 | Không có họ địa chỉ và bật cả hai bit FIRST. |
| 15 | Có cả hai họ nhưng bật đồng thời `IPV4_FIRST` và `IPV6_FIRST`. |

Ví dụ kiểm tra:

~~~java
LookupPolicy.of(0);
LookupPolicy.of(LookupPolicy.IPV4_FIRST);
LookupPolicy.of(LookupPolicy.IPV6_FIRST);

LookupPolicy.of(LookupPolicy.IPV4 | LookupPolicy.IPV6
        | LookupPolicy.IPV4_FIRST | LookupPolicy.IPV6_FIRST);
~~~

Không nên tự thêm bit ngoài bốn hằng số được API công khai định nghĩa. Ý nghĩa và tính hợp lệ của các bit không được tài liệu hóa không phải hợp đồng mà ứng dụng có thể dựa vào.

## 5. Ví dụ Java 18+: tạo và kiểm tra các tổ hợp

Ví dụ này tạo đủ chín policy hợp lệ, in mask ở dạng thập phân/nhị phân, rồi kiểm tra một số trường hợp không hợp lệ. Chương trình chỉ kiểm tra API tạo policy; nó không thực hiện truy vấn DNS.

Lưu thành `LookupPolicyOfDemo.java`:

~~~java
import java.net.spi.InetAddressResolver.LookupPolicy;

public final class LookupPolicyOfDemo {
    private static final int[] FAMILIES = {
            LookupPolicy.IPV4,
            LookupPolicy.IPV6,
            LookupPolicy.IPV4 | LookupPolicy.IPV6
    };

    private static final String[] FAMILY_NAMES = {
            "IPv4 only",
            "IPv6 only",
            "IPv4 + IPv6"
    };

    private static final int[] ORDERS = {
            0,
            LookupPolicy.IPV4_FIRST,
            LookupPolicy.IPV6_FIRST
    };

    private static final String[] ORDER_NAMES = {
            "system order",
            "IPv4 first",
            "IPv6 first"
    };

    private static String binary(int mask) {
        return String.format("%4s",
                Integer.toBinaryString(mask)).replace(' ', '0');
    }

    private static void showValidPolicies() {
        for (int i = 0; i < FAMILIES.length; i++) {
            for (int j = 0; j < ORDERS.length; j++) {
                int mask = FAMILIES[i] | ORDERS[j];

                // Factory kiểm tra mask và tạo LookupPolicy.
                LookupPolicy policy = LookupPolicy.of(mask);

                // characteristics() trả lại tập cờ của policy.
                int actual = policy.characteristics();
                if (actual != mask) {
                    throw new AssertionError("Unexpected characteristics");
                }

                System.out.printf(
                        "%-12s %-13s mask=%2d (0b%s)%n",
                        FAMILY_NAMES[i], ORDER_NAMES[j],
                        actual, binary(actual));
            }
        }
    }

    private static void expectInvalid(String label, int mask) {
        try {
            LookupPolicy.of(mask);
            throw new AssertionError(
                    label + " should have been rejected");
        } catch (IllegalArgumentException expected) {
            System.out.println(label + " -> IllegalArgumentException");
        }
    }

    public static void main(String[] args) {
        System.out.println("Valid policies:");
        showValidPolicies();

        System.out.println();
        System.out.println("Invalid policies:");
        expectInvalid("No address family", 0);
        expectInvalid("IPv4_FIRST without family",
                LookupPolicy.IPV4_FIRST);
        expectInvalid("IPv6_FIRST without family",
                LookupPolicy.IPV6_FIRST);
        expectInvalid("Both ordering flags",
                LookupPolicy.IPV4 | LookupPolicy.IPV6
                        | LookupPolicy.IPV4_FIRST
                        | LookupPolicy.IPV6_FIRST);
    }
}
~~~

Biên dịch và chạy bằng JDK 18 trở lên:

~~~shell
javac LookupPolicyOfDemo.java
java LookupPolicyOfDemo
~~~

Kết quả có dạng:

~~~text
Valid policies:
IPv4 only    system order  mask= 1 (0b0001)
IPv4 only    IPv4 first    mask= 5 (0b0101)
IPv4 only    IPv6 first    mask= 9 (0b1001)
IPv6 only    system order  mask= 2 (0b0010)
IPv6 only    IPv4 first    mask= 6 (0b0110)
IPv6 only    IPv6 first    mask=10 (0b1010)
IPv4 + IPv6  system order  mask= 3 (0b0011)
IPv4 + IPv6  IPv4 first    mask= 7 (0b0111)
IPv4 + IPv6  IPv6 first    mask=11 (0b1011)

Invalid policies:
No address family -> IllegalArgumentException
IPv4_FIRST without family -> IllegalArgumentException
IPv6_FIRST without family -> IllegalArgumentException
Both ordering flags -> IllegalArgumentException
~~~

Điều cần quan sát:

- Mỗi policy hợp lệ đều có ít nhất một bit họ địa chỉ.
- Không policy nào chứa đồng thời hai bit FIRST.
- `characteristics()` cho phép đọc lại mask đã tạo.
- `of(...)` không gọi resolver; không cần mạng hoặc hostname để kiểm chứng các quy tắc này.

## 6. Dùng policy trong một resolver

Sau khi tạo policy, JDK truyền nó vào `lookupByName`. Implementation cần dùng hai nhóm bit cho hai việc riêng:

1. Lọc địa chỉ: giữ IPv4 nếu `IPV4` bật; giữ IPv6 nếu `IPV6` bật.
2. Sắp xếp: nếu `IPV4_FIRST` bật thì đặt nhóm IPv4 trước; nếu `IPV6_FIRST` bật thì đặt nhóm IPv6 trước; nếu không có bit FIRST thì giữ system order.

Ví dụ logic rút gọn:

~~~java
int flags = policy.characteristics();

boolean needIpv4 = (flags & LookupPolicy.IPV4) != 0;
boolean needIpv6 = (flags & LookupPolicy.IPV6) != 0;
boolean ipv4First = (flags & LookupPolicy.IPV4_FIRST) != 0;
boolean ipv6First = (flags & LookupPolicy.IPV6_FIRST) != 0;

// Lọc candidates theo needIpv4 và needIpv6.
// Sau đó, nếu ipv4First thì nhóm IPv4 đứng trước.
// Nếu ipv6First thì nhóm IPv6 đứng trước.
// Nếu cả hai đều false thì giữ system order.
~~~

Không dùng phép so sánh bằng để kiểm tra riêng một bit:

~~~java
// Sai khi flags chứa nhiều cờ cùng lúc:
if (flags == LookupPolicy.IPV4) {
    // ...
}

// Đúng:
if ((flags & LookupPolicy.IPV4) != 0) {
    // ...
}
~~~

Cũng không dùng `&&` hoặc `||` để ghép mask. Hai toán tử đó trả về boolean; phép OR bit cần dùng `|`. Phép AND bit cần dùng `&`.

## 7. Phân biệt policy do ứng dụng tạo với policy mặc định của nền tảng

`LookupPolicy.of(...)` tạo một policy từ các cờ do caller chỉ định. Nó không thay đổi cấu hình toàn JVM và cũng không ghi system property.

JDK có policy mặc định ở phạm vi nền tảng; cách khởi tạo policy này chịu ảnh hưởng bởi cấu hình mạng và các system properties liên quan đến IPv4/IPv6, chẳng hạn `java.net.preferIPv4Stack` và `java.net.preferIPv6Addresses`. Đây là cơ chế lựa chọn mặc định của `InetAddress`.

Nếu ứng dụng tự tạo policy và truyền nó vào resolver, resolver phải thực hiện đúng policy nhận được. Đừng nhầm việc đặt `java.net.preferIPv6Addresses` với việc gọi `LookupPolicy.of(IPV4 | IPV6 | IPV6_FIRST)`: một bên cấu hình mặc định nền tảng, bên kia tạo một đối tượng policy cụ thể.

## 8. Lỗi thường gặp và cách tránh

| Lỗi | Hệ quả | Cách đúng |
|---|---|---|
| Chỉ truyền `IPV4_FIRST` hoặc `IPV6_FIRST` | Không có họ địa chỉ được yêu cầu; factory từ chối. | Bật ít nhất `IPV4` hoặc `IPV6`. |
| Bật cả hai bit FIRST | Hai thứ tự xung đột; factory từ chối. | Chọn một thứ tự hoặc system order. |
| Dùng `+` để kết hợp cờ | Phép cộng không biểu đạt rõ ý nghĩa bitmask và dễ sai khi lặp cờ. | Dùng OR bit `|`. |
| Dùng `==` để kiểm tra một cờ trong mask | Không nhận ra cờ khi có nhiều bit cùng bật. | Dùng AND bit `&`. |
| Nghĩ `of(...)` thực hiện lookup | Dễ thiết kế chương trình chờ mạng ở sai bước. | Dùng policy sau đó trong `lookupByName`. |
| Cho rằng FIRST có ý nghĩa khi chỉ có một họ | Diễn giải nhầm thứ tự. | Hiểu rằng cờ thứ tự không tạo ra địa chỉ thuộc họ còn lại. |
| Ghi số mask khó hiểu | Mã khó bảo trì. | Kết hợp các hằng số có tên. |
| Tự dùng bit ngoài API công khai | Dựa vào hành vi không được bảo đảm. | Chỉ dùng bốn cờ được tài liệu hóa. |

## 9. Checklist và câu hỏi tự đánh giá

Trước khi dùng policy, hãy xác minh:

- [ ] Có ít nhất một trong hai cờ `IPV4` hoặc `IPV6`.
- [ ] Không bật đồng thời `IPV4_FIRST` và `IPV6_FIRST`.
- [ ] Các cờ được ghép bằng phép OR theo bit.
- [ ] Các cờ được đọc bằng phép AND theo bit.
- [ ] Resolver lọc đúng họ địa chỉ trước khi trả kết quả.
- [ ] Resolver tôn trọng thứ tự FIRST hoặc system order.
- [ ] Kiểm thử cả trường hợp hợp lệ lẫn `IllegalArgumentException`.

Câu hỏi tự đánh giá:

1. Vì sao `LookupPolicy.of(0)` không hợp lệ?
2. Mask nào yêu cầu cả IPv4 và IPv6, đồng thời ưu tiên IPv6?
3. Vì sao `IPV4 | IPV6 | IPV4_FIRST | IPV6_FIRST` bị từ chối?
4. Có thể tạo policy chỉ IPv4 nhưng kèm `IPV6_FIRST` không? Điều gì xảy ra với thứ tự kết quả?
5. `characteristics()` có thực hiện tra cứu tên hay không?
6. Vì sao không nên dùng `flags == LookupPolicy.IPV4` để kiểm tra bit IPv4?

**Ghi nhớ:** `LookupPolicy.of(int)` nhận bitmask có ít nhất một cờ họ địa chỉ (`IPV4` hoặc `IPV6`), và không được đồng thời có hai cờ thứ tự (`IPV4_FIRST`, `IPV6_FIRST`). Ba lựa chọn họ địa chỉ kết hợp ba lựa chọn thứ tự tạo thành chín tổ hợp hợp lệ. Dùng các hằng số có tên để tạo mask, rồi truyền policy vào `lookupByName` để resolver lọc và sắp xếp địa chỉ.

## Tài liệu tham khảo chính thức

- [OpenJDK JEP 418 – Internet-Address Resolution SPI](https://openjdk.org/jeps/418).
- [Java SE 26: `InetAddressResolver.LookupPolicy` – `of(int)` và `characteristics()`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/spi/InetAddressResolver.LookupPolicy.html).
- [Java SE 26: Constant Field Values – các giá trị IPV4, IPV6, IPV4_FIRST, IPV6_FIRST](https://docs.oracle.com/en/java/javase/26/docs/api/constant-values.html).
- [Java SE 26: `InetAddressResolver` – hợp đồng `lookupByName`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/spi/InetAddressResolver.html).
