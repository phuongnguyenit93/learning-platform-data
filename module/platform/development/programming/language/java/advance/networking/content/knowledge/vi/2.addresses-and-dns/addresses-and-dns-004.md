# Tạo địa chỉ từ byte hoặc IP literal mà không nhầm với phân giải tên

## 1. Nhận diện đúng ba loại đầu vào

Trong Java networking, `java.net.InetAddress` biểu diễn **địa chỉ IP** (IPv4: 32 bit; IPv6: 128 bit), có thể đi kèm thông tin tên máy. Ba dạng dữ liệu thường xuất hiện cạnh nhau nhưng có hành vi khác nhau:

- **Byte địa chỉ**: bốn byte IPv4 hoặc mười sáu byte IPv6 lấy từ gói tin, giao thức hoặc cấu hình nhị phân. Các byte đã là địa chỉ; không cần hỏi DNS để biết IP.
- **IP literal**: chuỗi viết trực tiếp địa chỉ, ví dụ `192.0.2.42` hoặc `2001:db8::1`. Cần *phân tích cú pháp địa chỉ* (parse), không cần phân giải tên nếu chuỗi thực sự là literal hợp lệ.
- **Hostname**: chuỗi như `api.example.com`. Chương trình phải dùng dịch vụ phân giải tên của hệ điều hành/JVM để tìm IP; nguồn có thể là hosts file, bộ nhớ đệm hoặc DNS, nên không thể khẳng định mỗi lần gọi đều phát sinh một truy vấn DNS.

Phân biệt hai thao tác: **parse literal** chuyển biểu diễn của một IP đã biết thành đối tượng; **name resolution** tìm IP tương ứng với một tên. Việc tạo được `InetAddress` không đồng nghĩa với máy đích đang tồn tại, có kết nối mạng, hoặc địa chỉ đã được xác thực.

```text
byte[4]/byte[16] -- getByAddress(...) --> InetAddress
IP literal       -- getByName(literal) --> InetAddress (parse cú pháp)
hostname         -- getByName(hostname) --> name service/cache --> InetAddress
```

Các dải `192.0.2.0/24`, `203.0.113.0/24` và `2001:db8::/32` dùng cho tài liệu/ví dụ; không xem chúng là các máy chủ có thể truy cập.

## 2. Chọn API theo mục đích

| API Java 17+ | Đầu vào và hành vi tại thời điểm gọi | Có thể phân giải tên? |
| --- | --- | --- |
| `InetAddress.getByAddress(byte[])` | Chuyển 4/16 byte theo thứ tự mạng thành địa chỉ IP | **Không**; không reverse lookup |
| `InetAddress.getByAddress(String host, byte[])` | Dùng byte làm IP và **gắn nhãn hostname được cung cấp**, không kiểm tra nhãn | **Không** khi tạo |
| `InetAddress.getByName("192.0.2.42")` | Phân tích IP literal IPv4 hợp lệ | **Không** cần name service |
| `InetAddress.getByName("2001:db8::1")` | Phân tích IP literal IPv6 hợp lệ | **Không** cần name service |
| `InetAddress.getByName("api.example.com")` | Tìm IP cho hostname | **Có thể**, qua resolver/cache |
| `InetAddress.getAllByName(hostname)` | Tìm các địa chỉ được trả về cho tên | **Có thể**, qua resolver/cache |
| `address.getAddress()` / `address.getHostAddress()` | Lấy byte IP / chuỗi IP của đối tượng đã có | **Không** |
| `address.getHostName()` / `getCanonicalHostName()` | Lấy hostname; có thể cần reverse lookup nếu không có tên được nhớ sẵn | **Có thể** |

**Điểm dễ nhầm:** `getByName` không có nghĩa là "luôn gọi DNS". Nó chấp nhận **cả literal lẫn hostname**. Ngược lại, `getByAddress(String host, byte[] ip)` không phân giải `host` và cũng không kiểm chứng xem tên đó có trỏ đến `ip` hay không.

## 3. Tạo IPv4/IPv6 từ byte

`InetAddress.getByAddress(raw)` yêu cầu:

1. `raw.length == 4` đối với IPv4 hoặc `raw.length == 16` đối với IPv6. Độ dài khác dẫn tới `UnknownHostException`, ở đây là **lỗi dữ liệu địa chỉ**, không phải bằng chứng truy vấn DNS thất bại.
2. Byte được xếp theo **network byte order**: byte có trọng số lớn nhất đi trước. Với `192.0.2.42`, thứ tự là `192, 0, 2, 42`.
3. `byte` của Java là số có dấu trong khoảng -128 đến 127. Octet mạng lại có giá trị 0–255; vì vậy viết `(byte) 192` và đọc ngược bằng `b & 0xFF`.

Ví dụ sau chạy độc lập trên Java 17 trở lên, **không cần mạng/DNS**, vì chỉ sử dụng byte và các literal hợp lệ.

**`AddressCreationDemo.java`**

```java
import java.net.Inet4Address;
import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.UnknownHostException;

public class AddressCreationDemo {
    public static void main(String[] args) throws UnknownHostException {
        // IPv4: 192.0.2.42. Cast vì 192 vượt giới hạn byte có dấu.
        byte[] v4Raw = {(byte) 192, 0, 2, 42};
        InetAddress fromBytesV4 = InetAddress.getByAddress(v4Raw);
        InetAddress fromLiteralV4 = InetAddress.getByName("192.0.2.42");

        // IPv6: 2001:db8::1, đủ 16 byte theo network byte order.
        byte[] v6Raw = {
                0x20, 0x01, 0x0d, (byte) 0xb8,
                0, 0, 0, 0,
                0, 0, 0, 0,
                0, 0, 0, 1
        };
        InetAddress fromBytesV6 = InetAddress.getByAddress(v6Raw);
        InetAddress fromLiteralV6 = InetAddress.getByName("2001:db8::1");

        System.out.println("IPv4: " + fromBytesV4.getHostAddress());
        System.out.println("IPv4 family: "
                + (fromBytesV4 instanceof Inet4Address));
        System.out.println("IPv4 same: " + fromBytesV4.equals(fromLiteralV4));
        System.out.println("First octet: "
                + (fromBytesV4.getAddress()[0] & 0xFF));

        System.out.println("IPv6 family: "
                + (fromBytesV6 instanceof Inet6Address));
        System.out.println("IPv6 size: " + fromBytesV6.getAddress().length);
        System.out.println("IPv6 same: " + fromBytesV6.equals(fromLiteralV6));

        // Nhãn host không được phân giải hoặc xác thực khi tạo.
        InetAddress tagged =
                InetAddress.getByAddress("example.invalid", v4Raw);
        System.out.println("Tagged IP: " + tagged.getHostAddress());
        System.out.println("Tagged equal: " + tagged.equals(fromBytesV4));

        try {
            InetAddress.getByAddress(new byte[] {1, 2, 3});
        } catch (UnknownHostException e) {
            System.out.println("Invalid length: rejected");
        }
    }
}
```

Chạy:

```bash
javac --release 17 AddressCreationDemo.java
java AddressCreationDemo
```

Kết quả:

```text
IPv4: 192.0.2.42
IPv4 family: true
IPv4 same: true
First octet: 192
IPv6 family: true
IPv6 size: 16
IPv6 same: true
Tagged IP: 192.0.2.42
Tagged equal: true
Invalid length: rejected
```

Giải thích:

- Hai cách tạo IPv4 trả về các đối tượng cùng **giá trị IP**. `equals` so sánh nội dung địa chỉ, không dùng nhãn host làm danh tính của IP.
- Hai cách tạo IPv6 cũng chứa cùng 16 byte. Tránh so chuỗi IPv6 như tiêu chí duy nhất, vì literal có thể viết rút gọn (`::`), còn `getHostAddress()` có thể trả cách trình bày khác.
- `getByAddress("example.invalid", v4Raw)` vẫn tạo ra `192.0.2.42`; tên được gắn vào là metadata chưa được kiểm chứng.
- `UnknownHostException` ở trường hợp ba byte chỉ phản ánh độ dài không hợp lệ.

## 4. Tạo từ IP literal mà không vô tình đi qua hostname

Với giá trị **đã biết chắc là literal hợp lệ**, có thể dùng:

```java
InetAddress ipv4 = InetAddress.getByName("198.51.100.10");
InetAddress ipv6 = InetAddress.getByName("2001:db8::a");
```

Hai lệnh này phân tích cú pháp địa chỉ, không cần tra cứu hostname. Tuy nhiên, **đừng dùng `getByName(untrustedInput)` như một bộ kiểm tra "chỉ cho phép IP"**:

- Nếu đầu vào là tên (hoặc bị xử lý như tên), API có thể gọi name service.
- Java 17 còn chấp nhận một số **dạng IPv4 rút gọn** (không nhất thiết đúng bốn octet `d.d.d.d`); một địa chỉ được API chấp nhận không đồng nghĩa đáp ứng chính sách định dạng đầu vào của ứng dụng.
- `getByName(null)` và `getByName("")` có hành vi trả về địa chỉ loopback; không được để dữ liệu thiếu đi qua API rồi hiểu nhầm là địa chỉ được cung cấp hợp lệ.
- `"192.0.2.42:443"` không phải IP literal; port thuộc `InetSocketAddress`. Dấu ngoặc vuông quanh IPv6 trong URI (`[2001:db8::1]`) là quy tắc của URI/endpoint; cần tách host và port trước khi áp dụng chính sách kiểm tra.

Nếu yêu cầu **IPv4 dotted-quad chuẩn, hoàn toàn không có lookup kể cả khi nhập sai**, hãy tự kiểm tra bốn octet rồi gọi `getByAddress`. Ví dụ dưới đây cố ý không chấp nhận octet có số 0 thừa ở đầu (trừ chính `"0"`).

**`StrictIpv4Parser.java`**

```java
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.UnknownHostException;
import java.util.List;

public final class StrictIpv4Parser {
    public static Inet4Address parse(String text)
            throws UnknownHostException {
        if (text == null) {
            throw new IllegalArgumentException("IPv4 is required");
        }

        String[] octets = text.split("\\.", -1);
        if (octets.length != 4) {
            throw new IllegalArgumentException("Expected four octets");
        }

        byte[] raw = new byte[4];
        for (int i = 0; i < octets.length; i++) {
            String part = octets[i];
            if (part.isEmpty() || part.length() > 3
                    || (part.length() > 1 && part.charAt(0) == '0')) {
                throw new IllegalArgumentException("Invalid octet: " + part);
            }

            // Chỉ chấp nhận ASCII '0'..'9', không trim ngầm.
            for (int j = 0; j < part.length(); j++) {
                char ch = part.charAt(j);
                if (ch < '0' || ch > '9') {
                    throw new IllegalArgumentException("Non-decimal octet");
                }
            }

            int value = Integer.parseInt(part);
            if (value > 255) {
                throw new IllegalArgumentException("Octet exceeds 255");
            }
            raw[i] = (byte) value;
        }

        // Đã xác thực đúng 4 byte: không có lý do để gọi resolver.
        return (Inet4Address) InetAddress.getByAddress(raw);
    }

    public static void main(String[] args) throws UnknownHostException {
        System.out.println(parse("203.0.113.7").getHostAddress());

        for (String value : List.of(
                "203.0.113.999",
                "203.0.113",
                "203.0.113.007",
                "example.com")) {
            try {
                parse(value);
                System.out.println(value + " => accepted");
            } catch (IllegalArgumentException e) {
                System.out.println(value + " => rejected");
            }
        }
    }
}
```

```bash
javac --release 17 StrictIpv4Parser.java
java StrictIpv4Parser
```

```text
203.0.113.7
203.0.113.999 => rejected
203.0.113 => rejected
203.0.113.007 => rejected
example.com => rejected
```

Bộ kiểm tra này có **phạm vi cố ý là IPv4 dotted-quad**; nó không phải bộ phân tích hostname hoặc IPv6. IPv6 có ngữ pháp phong phú (rút gọn `::`, địa chỉ nhúng IPv4, zone id); không nên kiểm tra IPv6 bằng một regex giản lược tự chế. Nếu hệ thống cần bảo đảm "literal-only" cho **cả IPv4 và IPv6** ở Java 17, dùng một parser IP chuyên dụng đã được kiểm thử hoặc dựng `InetAddress` từ 4/16 byte đã xác thực. API `InetAddress.ofLiteral(String)` được bổ sung từ **Java 22**, không dùng được khi biên dịch theo Java 17.

## 5. Phân giải tên thuận và ngược là hai việc riêng

- **Forward resolution**: `getByName("server.example.com")` hoặc `getAllByName(...)` cần tìm IP từ hostname. Kết quả có thể đến từ cache, hosts file hoặc DNS, phụ thuộc hệ thống và thời điểm; `getAllByName` có thể trả nhiều IP.
- **Reverse resolution**: `address.getHostName()` có thể tìm hostname từ địa chỉ nếu đối tượng không lưu sẵn tên; `getCanonicalHostName()` có thể thực hiện tra cứu để tìm tên chuẩn (best effort). Hai lệnh này không phù hợp với đường đi yêu cầu chỉ thao tác IP không phát sinh lookup.
- **Chỉ hiển thị IP**: dùng `getHostAddress()`; nếu cần so sánh giá trị, dùng `equals` hoặc `getAddress()`, không dựa vào hostname.
- **Gắn nhãn ≠ xác thực**: `getByAddress("trusted.example", raw)` ghi nhận chuỗi `trusted.example` mà không xác minh forward hay reverse DNS. Không dùng nhãn đó làm chứng cứ sở hữu địa chỉ, quyền truy cập, hay định danh bảo mật.
- **`toString()` không phải bộ mã hóa định dạng chuẩn**: nó có thể chứa phần hostname và dấu `/`; tránh parse ngược `InetAddress.toString()` để lấy IP hoặc hostname.

Ví dụ đối chiếu hành vi (đoạn mã minh họa, **không** cần thực thi hostname thật để hiểu):

```java
InetAddress raw = InetAddress.getByAddress(
        new byte[] {(byte) 192, 0, 2, 42});  // Không DNS

String ipText = raw.getHostAddress();       // "192.0.2.42", không DNS
String possiblyName = raw.getHostName();   // Có thể reverse lookup

InetAddress labeled = InetAddress.getByAddress(
        "app.example.invalid", raw.getAddress()); // Không kiểm tra hostname

// Lời gọi dưới đây có thể dùng resolver; không nằm trên đường đi offline.
// InetAddress named = InetAddress.getByName("api.example.com");
```

Trong hệ thống cần tính lặp lại, tránh đưa các lời gọi tra cứu tên ngược vào đường ghi log nóng, xử lý gói tin, so sánh IP hoặc logic kiểm tra truy cập. Name resolution có thể chậm, thất bại hoặc trả kết quả khác theo môi trường.

## 6. Địa chỉ IP, hostname và cổng kết nối

`InetAddress` không chứa port. `InetSocketAddress` ghép địa chỉ/tên với port nhưng **constructor được chọn ảnh hưởng việc tra cứu**:

| Cách tạo endpoint | Hệ quả |
| --- | --- |
| `new InetSocketAddress(existingInetAddress, 443)` | Địa chỉ IP đã biết; không cần resolve hostname khi tạo endpoint |
| `new InetSocketAddress("api.example.com", 443)` | Thử resolve hostname ngay khi tạo; có thể trả đối tượng `isUnresolved() == true` nếu không phân giải được |
| `InetSocketAddress.createUnresolved("api.example.com", 443)` | Chủ động giữ hostname chưa phân giải; không lookup lúc tạo; hữu ích khi một tầng khác (ví dụ proxy) sẽ xử lý tên |
| `socketAddress.getHostString()` | Lấy host/IP dạng chuỗi mà không kích hoạt reverse lookup |
| `socketAddress.getHostName()` | Có thể reverse lookup nếu endpoint được tạo từ IP literal |

Đoạn minh họa đặt **bên trong một phương thức có `throws UnknownHostException`** (không phải chương trình độc lập):

```java
InetAddress fixedIp = InetAddress.getByAddress(
        new byte[] {(byte) 192, 0, 2, 42});

InetSocketAddress direct = new InetSocketAddress(fixedIp, 443);
InetSocketAddress deferred =
        InetSocketAddress.createUnresolved("api.example.invalid", 443);

System.out.println(direct.isUnresolved());        // false
System.out.println(deferred.isUnresolved());      // true
System.out.println(deferred.getHostString());     // api.example.invalid
```

Đây chỉ là **tạo đối tượng endpoint**; gọi `Socket.connect(...)` hoặc gửi dữ liệu sau đó vẫn là thao tác mạng thực. Một endpoint `unresolved` không được bảo đảm kết nối trực tiếp thành công; nơi tiêu thụ nó phải biết cách xử lý hostname.

## 7. Các trường hợp nâng cao cần lưu ý

**IPv6 scope/zone:** Địa chỉ link-local như `fe80::1%3` cần xác định giao diện mạng phù hợp. Mười sáu byte IP thuần không mô tả đầy đủ zone. Khi cần giữ scope, dùng `Inet6Address.getByAddress(host, raw, scopeId)` hoặc biến thể nhận `NetworkInterface`, kiểm tra scope có ý nghĩa trên máy đang chạy. Không hardcode chỉ số giao diện giữa các máy. Các ví dụ `2001:db8::1` ở trên là IPv6 không scope.

**IPv4/IPv6 và môi trường:** Parse thành công không bảo đảm stack mạng thực tế hỗ trợ kết nối bằng phiên bản IP tương ứng. Đừng dùng kết quả kiểm tra `instanceof` để suy ra máy đích có thể truy cập. Cũng đừng giả định một hostname chỉ có một IP hay thứ tự địa chỉ phân giải luôn cố định.

**Dữ liệu chưa tin cậy:** Tách rõ chính sách "chỉ IP literal" và "cho phép hostname". Với hostname, kết quả resolve có thể thay đổi; nếu sử dụng để áp đặt quy tắc an ninh mạng, phải kiểm tra **IP thực tế được dùng để kết nối**, không chỉ kiểm tra chuỗi tên ban đầu. Nếu chỉ muốn đọc một IP do người dùng cung cấp mà không chấp nhận truy vấn DNS ngầm, nên parse literal trước bằng cách không thể rẽ vào resolver.

**Vấn đề lỗi:** `UnknownHostException` có thể chỉ dữ liệu IP dài sai ở `getByAddress` hoặc lỗi không tìm được tên ở `getByName(hostname)`. Cùng một kiểu exception nhưng **nguyên nhân và cách xử lý khác nhau**: lỗi byte length phải sửa input, lỗi resolver cần chính sách thời gian chờ/thử lại/thông báo riêng.

## 8. Bài tập tự kiểm tra

1. Có `byte[] {(byte) 203, 0, 113, 9}`. Hãy tạo `InetAddress` không lookup, in đúng chuỗi IP và in octet đầu dưới dạng 0–255.
2. `InetAddress.getByAddress("my-service.internal", bytes)` có khẳng định `my-service.internal` thực sự trỏ đến IP trong `bytes` không? Vì sao?
3. Một API nhận **chỉ IPv4 dotted-quad**, nhưng gọi thẳng `InetAddress.getByName(userInput)`. Hai rủi ro chính là gì?
4. Khi muốn hiển thị IP mà không tra tên ngược, hãy chọn `getHostAddress()` hay `getHostName()`. Khi tạo `InetSocketAddress` từ chuỗi hostname nhưng muốn hoãn lookup, chọn API nào?

**Đáp án:** (1) dùng `getByAddress`, `getHostAddress()` và `address.getAddress()[0] & 0xFF`, kết quả `203.0.113.9` và `203`; (2) không, hostname chỉ là nhãn chưa được xác thực; (3) chuỗi có thể bị coi là hostname và gọi resolver, đồng thời một số dạng IPv4 rút gọn được chấp nhận ngoài chính sách bốn octet; (4) `getHostAddress()` và `InetSocketAddress.createUnresolved(host, port)`.

## Tài liệu tham khảo

- [Java SE 17 — InetAddress](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetAddress.html): `getByAddress`, `getByName`, `getHostName`, `getHostAddress`.
- [Java SE 17 — Inet4Address](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Inet4Address.html): các dạng biểu diễn IPv4 được chấp nhận.
- [Java SE 17 — Inet6Address](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Inet6Address.html): IPv6 literal và scope.
- [Java SE 17 — InetSocketAddress](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetSocketAddress.html): resolved/unresolved endpoint và `getHostString()`.
