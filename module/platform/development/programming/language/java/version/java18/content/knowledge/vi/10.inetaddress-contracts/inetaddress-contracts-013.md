# java.net.preferIPv4Stack và java.net.preferIPv6Addresses: ảnh hưởng cần kiểm chứng theo JDK

> **Chương:** Hợp đồng `InetAddress` — **mô-đun:** `JAVA_VERSION_JAVA18`. Bài học phân biệt hai system properties điều khiển lựa chọn socket family và thứ tự ưu tiên địa chỉ IPv4/IPv6 trong networking stack của JDK. Cả hai vẫn được tài liệu hóa trên Java 18 và JDK hiện đại. Hành vi thực tế còn phụ thuộc hệ điều hành, resolver, cấu hình mạng và thư viện client.

Hai thuộc tính có tên gần giống nhau nhưng điều khiển hai quyết định khác nhau:

- `java.net.preferIPv4Stack` quyết định ứng dụng dùng socket IPv4-only hay socket IPv6 có khả năng dual-stack khi hệ điều hành hỗ trợ IPv6.
- `java.net.preferIPv6Addresses` quyết định thứ tự ưu tiên IPv4/IPv6 khi hostname có cả hai loại địa chỉ và cả hai family đều khả dụng.

Cả hai có mặc định `false` và được kiểm tra **một lần khi JVM khởi động**. Vì vậy, hãy cấu hình bằng tham số launcher `-D` hoặc cấu hình khởi chạy tương ứng; thay đổi `System.setProperty` sau khi JVM đã khởi tạo networking không phải cách đáng tin cậy để đổi hành vi.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt socket family với thứ tự địa chỉ trả về khi phân giải hostname.
2. Đọc đúng ba chế độ của `java.net.preferIPv6Addresses`: `false`, `true` và `system`.
3. Dự đoán ảnh hưởng của `java.net.preferIPv4Stack=true` tới kết nối IPv6-only và dual-stack server.
4. Cấu hình hai system properties trước khi JVM khởi động.
5. Quan sát địa chỉ qua `InetAddress.getAllByName` và phân biệt kết quả lookup với khả năng kết nối TCP.
6. Thiết kế phép thử riêng cho từng cấu hình, trên đúng JDK và môi trường mạng cần triển khai.

## 2. Hai thuộc tính điều khiển hai lớp khác nhau

| Thuộc tính | Quyết định chính | Mặc định | Thời điểm đọc |
|---|---|---:|---|
| `java.net.preferIPv4Stack` | Dùng socket IPv4-only hay socket IPv6 có khả năng dual-stack | `false` | Một lần lúc JVM khởi động |
| `java.net.preferIPv6Addresses` | Ưu tiên địa chỉ IPv4 hay IPv6 khi cả hai cùng khả dụng | `false` | Một lần lúc JVM khởi động |

Không dùng hai tên này thay thế cho nhau. Một thuộc tính liên quan đến loại socket native mà networking stack sử dụng; thuộc tính còn lại liên quan đến thứ tự ưu tiên địa chỉ trong kết quả phân giải tên.

## 3. java.net.preferIPv4Stack: lựa chọn socket IPv4-only hay dual-stack

### 3.1. Mặc định false

Khi IPv6 khả dụng trên hệ điều hành, mặc định JDK sử dụng socket IPv6. Trên nền tảng hỗ trợ dual-stack, socket này có thể kết nối tới và chấp nhận kết nối từ cả máy chủ IPv4 lẫn IPv6.

Đây là cách giúp một socket phục vụ hoặc kết nối tới cả hai họ địa chỉ mà không cần ứng dụng tạo riêng một socket IPv4 và một socket IPv6. Khả năng dual-stack cuối cùng vẫn phụ thuộc hỗ trợ của hệ điều hành và cấu hình socket trên nền tảng đó.

### 3.2. Đặt true

Nếu đặt `java.net.preferIPv4Stack=true`, ứng dụng yêu cầu sử dụng socket IPv4-only khi IPv4 khả dụng. Hệ quả quan trọng là ứng dụng không thể giao tiếp với host chỉ có IPv6 thông qua các socket đó.

Ví dụ:

```text
java -Djava.net.preferIPv4Stack=true -jar app.jar
```

Không bật tùy chọn này chỉ vì một hostname có địa chỉ IPv4. Nó là lựa chọn phạm vi giao thức của socket cho tiến trình, có thể ảnh hưởng cả client lẫn server trong cùng JVM.

### 3.3. Những gì thuộc tính này không làm

- Không bật IPv4 trên một hệ điều hành không có IPv4.
- Không sửa cấu hình interface, route, firewall hoặc NAT.
- Không tạo thêm bản ghi A cho hostname.
- Không làm một dịch vụ IPv6-only trở thành dịch vụ IPv4.
- Không thay thế việc kiểm tra khả năng dual-stack thực tế của hệ điều hành.

Nếu môi trường không có IPv4 hoặc IPv6, kết quả còn phụ thuộc các family mà hệ điều hành cung cấp và implementation JDK. Đừng hiểu tên thuộc tính là một lệnh cấu hình lại network stack của hệ điều hành.

## 4. java.net.preferIPv6Addresses: ưu tiên thứ tự địa chỉ

Thuộc tính này áp dụng khi một hostname có cả địa chỉ IPv4 và IPv6, và IPv6 khả dụng trên hệ điều hành.

| Giá trị | Ý nghĩa |
|---|---|
| `false` (mặc định) | Ưu tiên địa chỉ IPv4 trước để duy trì tương thích với ứng dụng cũ |
| `true` | Ưu tiên địa chỉ IPv6 trước khi có thể |
| `system` | Giữ thứ tự địa chỉ do system-wide resolver trả về |

Ví dụ hostname có hai bản ghi:

```text
service.example.test
    A     -> 192.0.2.40
    AAAA  -> 2001:db8::40
```

Với `false`, JDK mặc định ưu tiên IPv4 trước. Với `true`, JDK ưu tiên IPv6 trước nếu family này khả dụng. Với `system`, thứ tự từ system-wide resolver được giữ nguyên.

`192.0.2.0/24` và `2001:db8::/32` là các dải địa chỉ dành cho tài liệu; ví dụ không đại diện máy chủ công cộng có thể kết nối.

### 4.1. Thuộc tính này không bật IPv6

Đặt `java.net.preferIPv6Addresses=true` không tự bật IPv6 trên máy, không cấp IPv6 cho interface và không tạo bản ghi AAAA. Nếu OS không hỗ trợ IPv6 hoặc hostname không có địa chỉ IPv6, JDK không thể ưu tiên một địa chỉ IPv6 không tồn tại.

Nó cũng không bảo đảm kết nối TCP sẽ thành công qua IPv6. Route, firewall, dịch vụ đích, chính sách mạng và cách client thử các địa chỉ vẫn quyết định kết quả kết nối.

### 4.2. system là giữ thứ tự resolver, không phải ưu tiên IPv6

`java.net.preferIPv6Addresses=system` không có nghĩa “ưu tiên IPv6 theo cấu hình hệ điều hành”. Nó yêu cầu giữ thứ tự địa chỉ mà system-wide resolver trả về. Resolver có thể trả IPv4 trước hoặc IPv6 trước tùy hệ điều hành và cấu hình của nó.

## 5. Cách hai thuộc tính tương tác

`java.net.preferIPv4Stack` giới hạn family socket; `java.net.preferIPv6Addresses` sắp thứ tự family địa chỉ khi cần cả hai. Khi cấu hình đồng thời, cần đọc chúng theo thứ tự:

1. Xác định OS có hỗ trợ IPv4 và IPv6 hay không.
2. Xác định socket stack có bị giới hạn IPv4-only bởi `preferIPv4Stack` hay không.
3. Chỉ khi cả hai family cùng được dùng, `preferIPv6Addresses` mới quyết định thứ tự ưu tiên.

| `preferIPv4Stack` | `preferIPv6Addresses` | Cách hiểu |
|---|---|---|
| `false` | `false` | Mặc định dual-stack khi OS hỗ trợ; IPv4 được ưu tiên trước |
| `false` | `true` | Dual-stack khi OS hỗ trợ; IPv6 được ưu tiên trước |
| `false` | `system` | Dual-stack khi OS hỗ trợ; giữ thứ tự resolver hệ thống |
| `true` | `false` | Yêu cầu socket IPv4-only; không thể dùng IPv6-only host |
| `true` | `true` | Yêu cầu IPv4-only; ưu tiên IPv6 không thể mở rộng family đã bị giới hạn |
| `true` | `system` | Yêu cầu IPv4-only; thứ tự resolver không biến socket thành dual-stack |

Nếu `preferIPv4Stack=true` và OS có IPv4, lựa chọn IPv4-only chi phối nhu cầu socket. Đặt thêm `preferIPv6Addresses=true` không khôi phục khả năng kết nối IPv6-only.

## 6. Cấu hình đúng thời điểm: trước khi JVM khởi động

Tài liệu Networking Properties quy định cả hai thuộc tính chỉ được kiểm tra một lần khi khởi động. Vì vậy, cách cấu hình thông thường là tham số `-D` của launcher.

Ví dụ từng cấu hình:

```text
# Mặc định: dual-stack khi hệ điều hành hỗ trợ, IPv4 trước
java -Djava.net.preferIPv4Stack=false -Djava.net.preferIPv6Addresses=false -jar app.jar

# Dual-stack, ưu tiên IPv6 trước
java -Djava.net.preferIPv4Stack=false -Djava.net.preferIPv6Addresses=true -jar app.jar

# Yêu cầu socket IPv4-only
java -Djava.net.preferIPv4Stack=true -jar app.jar

# Dual-stack, giữ thứ tự system resolver
java -Djava.net.preferIPv6Addresses=system -jar app.jar
```

### 6.1. System.setProperty sau startup không phải cách đổi chính sách

Ví dụ sau không bảo đảm thay đổi networking policy:

```java
System.setProperty("java.net.preferIPv6Addresses", "true");
```

Nếu thuộc tính đã được JDK đọc trong giai đoạn startup, thay đổi sau đó không làm policy được khởi tạo đọc lại. Tương tự, đọc `System.getProperty` sau khi gọi setter chỉ cho biết giá trị trong system properties; nó không chứng minh networking stack đã thay đổi lựa chọn family hoặc thứ tự địa chỉ.

Để so sánh các giá trị, chạy mỗi cấu hình trong một JVM mới. Không cần dùng `Security.setProperty` cho hai thuộc tính này: chúng là **system properties**, khác với `networkaddress.cache.ttl` và `networkaddress.cache.negative.ttl` vốn là security properties.

## 7. Quan sát giá trị cấu hình trong tiến trình

Đoạn code sau in giá trị tường minh của hai system properties:

```java
public class IpPreferenceSettings {
    public static void main(String[] args) {
        System.out.println("java.version = " +
                System.getProperty("java.version"));
        System.out.println("java.vendor = " +
                System.getProperty("java.vendor"));
        System.out.println("java.net.preferIPv4Stack = " +
                System.getProperty("java.net.preferIPv4Stack"));
        System.out.println("java.net.preferIPv6Addresses = " +
                System.getProperty("java.net.preferIPv6Addresses"));
    }
}
```

Nếu một property trả về `null`, nghĩa là chưa có giá trị tường minh trong System Properties; tài liệu JDK mô tả mặc định của cả hai là `false`. Giá trị đọc được không chứng minh OS có IPv6, dual-stack đang được bật hoặc route thực tế hoạt động.

## 8. Kiểm tra thứ tự địa chỉ từ resolver

Dùng `InetAddress.getAllByName` để xem toàn bộ địa chỉ mà JVM trả về cho một hostname:

```java
import java.net.Inet4Address;
import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.UnknownHostException;

public class AddressOrderProbe {
    public static void main(String[] args) throws UnknownHostException {
        if (args.length != 1) {
            throw new IllegalArgumentException("Cần truyền hostname");
        }

        InetAddress[] addresses = InetAddress.getAllByName(args[0]);
        for (int i = 0; i < addresses.length; i++) {
            InetAddress address = addresses[i];
            String family = address instanceof Inet4Address ? "IPv4"
                    : address instanceof Inet6Address ? "IPv6"
                    : "Unknown";

            System.out.printf("%d. %-7s %s%n",
                    i + 1, family, address.getHostAddress());
        }
    }
}
```

Chạy với một hostname thử nghiệm có cả A và AAAA record:

```text
java AddressOrderProbe.java service.example.test
```

Kết quả phụ thuộc DNS, system resolver, network stack, JDK và cấu hình startup. Để kiểm tra `preferIPv6Addresses`, so sánh thứ tự của danh sách trong các JVM riêng chạy với `false`, `true` và `system`. Một hostname chỉ có A record hoặc chỉ có AAAA record không đủ để kiểm tra thứ tự ưu tiên giữa hai family.

`InetAddress.getByName` chỉ trả về một địa chỉ; khi kiểm tra thứ tự, hãy dùng `getAllByName`. Không hard-code thứ tự hoặc địa chỉ IP cụ thể làm kỳ vọng cho mọi máy.

## 9. Kiểm tra khả năng kết nối thực tế

Danh sách địa chỉ được phân giải và khả năng kết nối TCP là hai bước khác nhau. Sau khi quan sát địa chỉ, hãy thử kết nối tới endpoint dual-stack mà bạn quản lý hoặc được phép kiểm thử.

```java
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Socket;

public class ConnectEachAddress {
    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            throw new IllegalArgumentException("Cần hostname và port");
        }

        String host = args[0];
        int port = Integer.parseInt(args[1]);

        for (InetAddress address : InetAddress.getAllByName(host)) {
            try (Socket socket = new Socket()) {
                socket.connect(new InetSocketAddress(address, port), 2_000);
                System.out.printf("CONNECTED %-24s %s%n",
                        address.getHostAddress(),
                        socket.getRemoteSocketAddress());
            } catch (IOException e) {
                System.out.printf("FAILED    %-24s %s: %s%n",
                        address.getHostAddress(),
                        e.getClass().getSimpleName(),
                        e.getMessage());
            }
        }
    }
}
```

Ví dụ chạy:

```text
java ConnectEachAddress.java service.example.test 443
```

Đây là phép thử từng địa chỉ tuần tự, không phải triển khai Happy Eyeballs. Một ứng dụng HTTP hoặc thư viện client có thể có chiến lược thử lại, timeout hoặc kết nối song song riêng. Đừng dùng kết quả của đoạn probe này để kết luận mọi client Java sẽ chọn cùng một địa chỉ.

## 10. Ảnh hưởng khi tạo server socket

`java.net.preferIPv4Stack` cũng có thể ảnh hưởng socket phía server:

- Với dual-stack socket và OS hỗ trợ, một socket IPv6 wildcard có thể nhận kết nối IPv4 lẫn IPv6.
- Với `preferIPv4Stack=true`, socket IPv4-only không thể nhận kết nối tới địa chỉ IPv6-only.

Nếu server phải phục vụ cả client IPv4 và IPv6, hãy kiểm tra socket bind thực tế, OS và firewall. Đừng chỉ dựa vào giá trị system property hoặc giả định mọi hệ điều hành xử lý dual-stack giống hệt nhau.

Một phép kiểm thử phù hợp là chạy server trong JVM với từng cấu hình, ghi địa chỉ bind, rồi thử kết nối từ client IPv4 và client IPv6 độc lập. Nếu dùng container, kiểm tra network namespace và port mapping của container; property của JVM không tự mở IPv6 cho container.

## 11. Những điều hai thuộc tính không kiểm soát

| Thành phần | Hai thuộc tính có điều khiển không? |
|---|---|
| DNS có bản ghi A/AAAA nào | Không |
| Interface có IPv4/IPv6 được cấu hình hay không | Không |
| Route tới mạng IPv4/IPv6 | Không |
| Firewall, security group, NAT | Không |
| DNS positive/negative cache TTL | Không |
| Thứ tự resolver trả địa chỉ (trong phạm vi `preferIPv6Addresses`) | Có ảnh hưởng theo lựa chọn ưu tiên |
| Socket family mà JDK yêu cầu (trong phạm vi `preferIPv4Stack`) | Có ảnh hưởng |
| Chiến lược retry/Happy Eyeballs của mọi thư viện client | Không bảo đảm |

Đặc biệt, `java.net.preferIPv6Addresses` không thay thế việc thiết kế fallback. Nếu địa chỉ IPv6 được ưu tiên nhưng đường IPv6 không hoạt động, ứng dụng cần có chiến lược kết nối phù hợp; chỉ đổi thứ tự địa chỉ không bảo đảm fallback đủ nhanh.

## 12. Quy trình kiểm chứng theo JDK và môi trường

1. **Ghi nhận runtime:** lưu `java.vendor`, `java.runtime.version`, `java.vm.version` và `java.home`.
2. **Ghi nhận OS/network:** kiểm tra OS hỗ trợ IPv4/IPv6, interface, route và firewall trong môi trường chạy thật.
3. **Tạo endpoint dual-stack thử nghiệm:** bảo đảm cùng hostname có A và AAAA record, cả hai đầu cuối có dịch vụ lắng nghe.
4. **Chạy JVM mới cho từng cấu hình:** mặc định, IPv6 preference, system order và IPv4-only nếu cần.
5. **Quan sát resolver:** dùng `InetAddress.getAllByName` để ghi family và thứ tự.
6. **Thử TCP từng family:** kết nối tới endpoint IPv4 và IPv6 bằng cùng port hoặc port tương ứng.
7. **Thử server bind:** xác nhận server nhận được kết nối qua các family được yêu cầu.
8. **Lặp trong container/VM:** nếu triển khai ở đó, thực hiện phép thử ngay trong network namespace thực tế.
9. **Ghi nhận kết quả:** lưu tham số JVM, output địa chỉ, kết quả TCP và cấu hình OS để tái lập.

## 13. Bài tập tự kiểm tra

1. `java.net.preferIPv4Stack` khác `java.net.preferIPv6Addresses` ở quyết định nào?
2. Vì sao `preferIPv4Stack=true` có thể làm ứng dụng không kết nối được tới IPv6-only host?
3. `preferIPv6Addresses=true` có bật IPv6 trên OS không?
4. Giá trị `system` của `preferIPv6Addresses` giữ thứ tự nào?
5. Vì sao cả hai thuộc tính phải được đặt trước khi JVM khởi động?
6. Vì sao `System.setProperty` sau startup không phải phép thử hợp lệ cho hai thuộc tính này?
7. Vì sao phải dùng `InetAddress.getAllByName` thay vì `getByName` để quan sát thứ tự?
8. Nếu resolver trả IPv6 trước nhưng TCP connect thất bại, cần kiểm tra thêm những lớp nào?
9. Nếu server bind IPv4-only, điều gì xảy ra với client chỉ có IPv6?

**Tiêu chí hoàn thành:** Bạn phân biệt được socket family với thứ tự địa chỉ, cấu hình hai system properties lúc startup, quan sát được kết quả lookup và xác minh riêng khả năng TCP trên IPv4/IPv6 trong đúng môi trường triển khai.

## 14. Tài liệu chuẩn

- [Networking Properties — Java SE 18](https://docs.oracle.com/en/java/javase/18/docs/api/java.base/java/net/doc-files/net-properties.html): hợp đồng, mặc định và quy tắc chỉ đọc hai thuộc tính một lần khi startup.
- [Networking Properties — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/doc-files/net-properties.html): xác nhận hành vi hiện hành của IPv4/IPv6 protocol properties.
- [Java Networking — Java SE 18](https://docs.oracle.com/en/java/javase/18/core/java-networking.html): mô tả socket dual-stack và lựa chọn địa chỉ IPv4/IPv6.
- [InetAddress — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/InetAddress.html): API phân giải tên và danh sách địa chỉ.
- [OpenJDK InetAddress source](https://github.com/openjdk/jdk/blob/master/src/java.base/share/classes/java/net/InetAddress.java): cách JDK hiện đại khởi tạo lookup policy từ hai system properties và trạng thái hỗ trợ của hệ điều hành.
