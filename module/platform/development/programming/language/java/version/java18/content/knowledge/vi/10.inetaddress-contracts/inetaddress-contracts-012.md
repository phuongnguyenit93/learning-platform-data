# Security property và system property: cấu hình cache đúng cơ chế và trước lần sử dụng đầu tiên

> **Chương:** Hợp đồng `InetAddress` — **mô-đun:** `JAVA_VERSION_JAVA18`. Bài học phân biệt Java Security Properties với System Properties khi cấu hình cache phân giải tên của `InetAddress`. Trọng tâm là đặt đúng property, chọn file cấu hình lúc khởi động và hoàn tất cấu hình trước khi cơ chế cache được khởi tạo. Các hướng dẫn áp dụng cho Java 18 và JDK hiện đại.

Hai khóa `networkaddress.cache.ttl` và `networkaddress.cache.negative.ttl` trông giống system properties vì tên có dạng key=value và thường xuất hiện trong tài liệu lệnh khởi chạy Java. Tuy nhiên, chúng là **security properties**. Vì thế, truyền `-Dnetworkaddress.cache.ttl=30` hoặc gọi `System.setProperty("networkaddress.cache.ttl", "30")` không cấu hình positive cache của `InetAddress`.

Có hai cách cấu hình đúng: đặt security property bằng `Security.setProperty` thật sớm trong bootstrap, trước lần phân giải tên đầu tiên; hoặc nạp security properties file khi JVM khởi động. Cách dùng file khởi động thường dễ kiểm soát và ổn định hơn vì thư viện hoặc framework có thể vô tình kích hoạt phân giải tên trước khi `main` chạy đến đoạn cấu hình.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt System Properties và Java Security Properties.
2. Giải thích vì sao `-Dnetworkaddress.cache.ttl` và `System.setProperty` không cấu hình address cache.
3. Dùng `Security.setProperty` đúng thời điểm nếu cần cấu hình trong mã.
4. Nạp file security properties bổ sung bằng `-Djava.security.properties` khi JVM khởi động.
5. Phân biệt cú pháp nạp bổ sung bằng `=` với cú pháp thay thế toàn bộ bằng `==`.
6. Kiểm tra property đã được nạp và thiết kế phép thử trong JVM mới.
7. Tránh dựa vào các cờ nội bộ hoặc reflection để sửa cache policy.

## 2. Hai loại property có hai không gian cấu hình

Java duy trì hai nhóm cấu hình khác nhau:

| Nhóm | API đọc/ghi | Ví dụ | Mục đích |
|---|---|---|---|
| System Properties | `System.getProperty` / `System.setProperty` | `user.timezone`, `file.encoding`, `java.security.properties` | Cấu hình tiến trình và một số hành vi runtime |
| Java Security Properties | `Security.getProperty` / `Security.setProperty` | `networkaddress.cache.ttl`, `networkaddress.cache.negative.ttl` | Cấu hình chính sách bảo mật và các thành phần đọc security properties |

Một tên property không tự cho biết nó thuộc nhóm nào. Phải đọc tài liệu của property. Riêng hai khóa address cache được Java Networking Properties mô tả rõ là security properties; chúng không được đặt bằng tùy chọn `-D` thông thường hoặc `System.setProperty`.

### 2.1. Phân biệt qua ví dụ

Giả sử chạy:

```text
java -Dnetworkaddress.cache.ttl=30 -jar app.jar
```

JVM tạo một System Property tên `networkaddress.cache.ttl` với giá trị `30`. Nhưng address cache đọc **Security Property** cùng tên. Hai không gian này tách biệt, nên việc nhìn thấy `30` qua `System.getProperty` không chứng minh `InetAddress` dùng TTL 30 giây.

Ví dụ kiểm tra cả hai:

```java
import java.security.Security;

public class PropertyNamespaces {
    public static void main(String[] args) {
        String key = "networkaddress.cache.ttl";

        System.out.println("System property   = " +
                System.getProperty(key));
        System.out.println("Security property = " +
                Security.getProperty(key));
    }
}
```

Nếu chạy với `-Dnetworkaddress.cache.ttl=30`, kết quả có thể có dạng:

```text
System property   = 30
Security property = null
```

`null` ở đây nghĩa là security property chưa được đặt tường minh trong cấu hình được đọc. Nó không có nghĩa TTL bằng 0 hoặc cache bị tắt; JDK có thể dùng mặc định của implementation.

## 3. Vì sao -D và System.setProperty không có tác dụng?

`-Dname=value` là cú pháp launcher để tạo System Property. Nó tương đương việc ứng dụng đọc giá trị bằng `System.getProperty(name)`. Trong khi đó, address cache lấy chính sách từ Java Security Properties.

Hai đoạn sau không cấu hình address cache:

```text
java -Dnetworkaddress.cache.ttl=30 -jar app.jar
```

```java
System.setProperty("networkaddress.cache.ttl", "30");
```

Chúng có thể làm người vận hành tưởng rằng TTL đã đổi vì giá trị System Property hiện ra khi kiểm tra, nhưng `InetAddress` không dùng System Property đó làm cấu hình chuẩn cho hai TTL.

### 3.1. Không nhầm với java.security.properties

Có một điểm dễ gây nhầm: `-Djava.security.properties` là System Property đặc biệt mà cơ chế bảo mật của JDK đọc để biết cần nạp thêm security properties file nào.

Vì vậy:

- `-Dnetworkaddress.cache.ttl=30`: đặt System Property sai namespace, không cấu hình address cache.
- `-Djava.security.properties=file:/.../custom.properties`: chỉ định file chứa Java Security Properties; nếu file có khóa address cache, chúng được nạp theo cơ chế bảo mật.

Dấu `-D` trong trường hợp thứ hai cấu hình **nguồn của security properties**, không trực tiếp đặt `networkaddress.cache.ttl` như một System Property.

## 4. Cách 1: đặt bằng Security.setProperty trước lần phân giải đầu tiên

`Security.setProperty(key, value)` đặt giá trị trong Java Security Properties của tiến trình hiện tại. Nếu muốn cấu hình bằng mã, phải đặt giá trị trước khi cơ chế address-cache policy đọc các property này.

### 4.1. Ví dụ tối giản

Tạo `ConfigureAddressCacheEarly.java`:

```java
import java.net.InetAddress;
import java.security.Security;

public class ConfigureAddressCacheEarly {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Cần truyền hostname");
        }

        // Cấu hình security properties trước lần name lookup đầu tiên.
        Security.setProperty("networkaddress.cache.ttl", "30");
        Security.setProperty("networkaddress.cache.negative.ttl", "5");

        System.out.println("Positive security property = " +
                Security.getProperty("networkaddress.cache.ttl"));
        System.out.println("Negative security property = " +
                Security.getProperty("networkaddress.cache.negative.ttl"));

        // Lần phân giải đầu tiên chỉ diễn ra sau khi cấu hình đã được đặt.
        for (InetAddress address : InetAddress.getAllByName(args[0])) {
            System.out.println(address.getHostAddress());
        }
    }
}
```

Chạy:

```text
java ConfigureAddressCacheEarly.java example.com
```

Ví dụ này minh họa thứ tự cấu hình trong một chương trình nhỏ: đặt security properties trước khi gọi API phân giải tên. Khi đưa vào ứng dụng lớn, phải kiểm tra liệu thư viện, logging appender, telemetry agent, HTTP client hoặc framework có thực hiện name lookup trước đoạn bootstrap này hay không.

### 4.2. Ranh giới trước lần sử dụng đầu tiên

Chính sách cache được thành phần networking đọc khi khởi tạo. Trong các implementation OpenJDK, các giá trị cache policy được nạp vào trạng thái nội bộ khi cơ chế policy được khởi tạo; chúng không phải cấu hình được đọc lại tùy ý cho mỗi lần gọi `InetAddress.getByName`.

Vì vậy, đặt `Security.setProperty` sau khi ứng dụng đã phân giải hostname không bảo đảm thay đổi chính sách cache đang hoạt động. Việc đọc lại `Security.getProperty` có thể cho thấy giá trị mới, nhưng điều đó không chứng minh cache policy đã khởi tạo được nạp lại.

Không có API công khai chung để yêu cầu `InetAddress` xóa cache và nạp lại toàn bộ TTL trong tiến trình đang chạy. Khi đã bỏ lỡ thời điểm bootstrap, cách kiểm thử đáng tin cậy là khởi động JVM mới với cấu hình mong muốn.

### 4.3. Khi nào nên dùng cách này?

Dùng `Security.setProperty` trong mã khi:

- Bạn sở hữu entry point và kiểm soát thứ tự khởi tạo.
- Chương trình nhỏ hoặc công cụ chạy độc lập.
- Có thể bảo đảm chưa có thư viện nào gọi API phân giải tên trước đoạn cấu hình.
- Bạn muốn cấu hình theo một lựa chọn ứng dụng tại bootstrap và có kiểm thử trên đúng JDK.

Không nên đặt rải rác trong request handler, factory tạo HTTP client hoặc mã nghiệp vụ. Cấu hình đến muộn sẽ khó dự đoán và khó tái lập.

## 5. Cách 2: nạp security properties file lúc JVM khởi động

Đối với ứng dụng server, ứng dụng dùng framework hoặc chương trình có nhiều dependency, cấu hình qua file trước khi JVM chạy thường là lựa chọn ổn định hơn.

### 5.1. File master của JDK

File security properties chính thường nằm tại:

```text
$JAVA_HOME/conf/security/java.security
```

File này thuộc JDK runtime đang chạy. Không giả định file ở JDK terminal giống file của IDE, service manager hoặc container. Có thể in `System.getProperty("java.home")` từ chính tiến trình để xác định runtime directory.

### 5.2. Tạo file bổ sung riêng cho ứng dụng

Tạo file `inetaddress-cache.properties`:

```properties
networkaddress.cache.ttl=30
networkaddress.cache.negative.ttl=5
```

Nạp file khi khởi động:

```text
java -Djava.security.properties=file:/opt/myapp/conf/inetaddress-cache.properties -jar app.jar
```

Trên Windows, dùng file URI hợp lệ, ví dụ:

```text
java -Djava.security.properties=file:///C:/myapp/conf/inetaddress-cache.properties -jar app.jar
```

Security properties file được nạp trong giai đoạn khởi tạo cấu hình bảo mật. Nhờ vậy, các giá trị address cache đã có trước khi code ứng dụng hoặc dependency thực hiện lookup hostname.

### 5.3. Một dấu bằng và hai dấu bằng

Hai cú pháp có ý nghĩa khác nhau:

| Cú pháp | Hành vi |
|---|---|
| `-Djava.security.properties=file:/path/custom.properties` | Nạp file bổ sung, kết hợp với master security properties |
| `-Djava.security.properties==file:/path/custom.properties` | Thay thế master security properties bằng file được chỉ định |

Khi chỉ muốn ghi đè hai TTL, thường dùng một dấu bằng để nạp file bổ sung. Dùng `==` có thể làm mất các security properties mặc định khác nếu file thay thế không khai báo lại chúng.

Không tạo file chỉ có hai khóa TTL rồi dùng cú pháp thay thế toàn bộ, trừ khi bạn thực sự muốn tự quản lý toàn bộ security properties của runtime và đã kiểm tra tác động.

### 5.4. Đặt cấu hình trong file master

Một lựa chọn khác là quản trị viên cập nhật trực tiếp file:

```text
$JAVA_HOME/conf/security/java.security
```

Thêm hoặc cập nhật:

```properties
networkaddress.cache.ttl=30
networkaddress.cache.negative.ttl=5
```

Cách này ảnh hưởng mọi ứng dụng dùng JDK installation đó, vì vậy cần phối hợp với quy trình quản trị runtime. Nếu các ứng dụng có yêu cầu TTL khác nhau, file bổ sung theo từng ứng dụng giúp tách cấu hình rõ hơn.

## 6. So sánh hai cách cấu hình đúng

| Tiêu chí | Security.setProperty | Security properties file lúc khởi động |
|---|---|---|
| Cơ chế | Ghi Java Security Property trong tiến trình | JDK nạp Java Security Properties từ file |
| Thời điểm | Phải trước khi address-cache policy được khởi tạo | Trước khi code ứng dụng chạy và trước lookup |
| Phụ thuộc thứ tự khởi tạo dependency | Có | Ít hơn; cấu hình đã có từ startup |
| Thích hợp | Công cụ nhỏ, entry point kiểm soát được | Server, ứng dụng framework, production deployment |
| Tái lập cấu hình | Cần bảo đảm code bootstrap luôn chạy đầu tiên | Có thể lưu file và tham số khởi chạy cùng deployment |
| Thay đổi trong tiến trình đang chạy | Không bảo đảm có hiệu lực sau lần sử dụng đầu | Thay đổi file cần khởi động tiến trình mới để nạp lại |

Nếu ứng dụng có nhiều thư viện, agent hoặc plugin, ưu tiên file cấu hình lúc khởi động. Nếu dùng `Security.setProperty`, hãy xem đó là cấu hình bootstrap một lần, không phải cơ chế đổi TTL động.

## 7. Cách kiểm tra cấu hình đã được nạp

### 7.1. Đọc security property

Dùng:

```java
import java.security.Security;

public class ShowAddressCacheSettings {
    public static void main(String[] args) {
        System.out.println("networkaddress.cache.ttl = " +
                Security.getProperty("networkaddress.cache.ttl"));
        System.out.println("networkaddress.cache.negative.ttl = " +
                Security.getProperty("networkaddress.cache.negative.ttl"));
    }
}
```

Chạy bằng đúng JDK và đúng tham số khởi chạy của ứng dụng. Kết quả cho biết security property đang được nhìn thấy trong tiến trình.

Nếu giá trị là `null`, hãy kiểm tra file master và file bổ sung, sau đó đối chiếu mặc định của vendor. Không chuyển `null` thành TTL bằng 0.

### 7.2. Đừng dùng System.getProperty làm bằng chứng

Đoạn sau chỉ kiểm tra System Properties:

```java
System.out.println(
        System.getProperty("networkaddress.cache.ttl"));
```

Nó không cho biết security property được address cache sử dụng. Khi kiểm tra, dùng `Security.getProperty` hoặc xem security properties đã nạp bằng tùy chọn chẩn đoán được JDK hỗ trợ.

### 7.3. Giá trị được đọc và policy đã khởi tạo là hai việc khác nhau

Nếu chương trình gọi `Security.setProperty` sau một lookup, `Security.getProperty` có thể hiển thị giá trị mới. Tuy nhiên, cache policy có thể đã lấy giá trị cũ khi khởi tạo. Vì vậy, readback của property không đủ chứng minh cấu hình có hiệu lực đối với cache đang chạy.

Để xác minh, chạy một JVM mới với file cấu hình đã chỉ định; thực hiện lookup lần đầu trong chính tiến trình đó và quan sát hành vi qua resolver fixture hoặc môi trường thử nghiệm được kiểm soát.

## 8. Ví dụ kiểm thử thứ tự khởi tạo

### 8.1. Trường hợp cấu hình đúng thứ tự

```java
import java.net.InetAddress;
import java.security.Security;

public class CorrectBootstrapOrder {
    public static void main(String[] args) throws Exception {
        Security.setProperty("networkaddress.cache.ttl", "0");
        Security.setProperty("networkaddress.cache.negative.ttl", "0");

        // Thực hiện name lookup sau khi đặt security properties.
        InetAddress.getAllByName("localhost");
    }
}
```

### 8.2. Trường hợp cấu hình quá muộn

```java
import java.net.InetAddress;
import java.security.Security;

public class LateBootstrapOrder {
    public static void main(String[] args) throws Exception {
        // Name lookup đầu tiên có thể khởi tạo cache policy.
        InetAddress.getAllByName("localhost");

        // Đặt sau lần lookup đầu không bảo đảm policy đang chạy thay đổi.
        Security.setProperty("networkaddress.cache.ttl", "0");
    }
}
```

Hai ví dụ thể hiện thứ tự gọi API. Trong ứng dụng thực tế, một dependency có thể đã gọi resolver trước cả hai đoạn mã. Do đó, không chỉ tìm lời gọi trực tiếp trong source; cần xem cả khởi tạo framework, telemetry, proxy, HTTP client và các thành phần chạy sớm.

## 9. Quy trình cấu hình cho môi trường thực tế

1. **Xác định runtime:** ghi nhận `java.vendor`, `java.runtime.version`, `java.vm.version` và `java.home` từ tiến trình ứng dụng.
2. **Chọn policy:** xác định positive TTL và negative TTL phù hợp với chu kỳ thay đổi endpoint, failover và khả năng chịu lỗi resolver.
3. **Chọn nguồn cấu hình:** ưu tiên file security properties được nạp khi JVM khởi động; chỉ dùng `Security.setProperty` nếu kiểm soát chắc chắn bootstrap.
4. **Cấu hình đúng namespace:** ghi hai khóa trong security properties; không truyền chúng trực tiếp bằng `-Dnetworkaddress.cache.*`.
5. **Kiểm tra file và launcher:** xác nhận `java.security.properties` trỏ tới đúng file và dùng đúng dấu bằng.
6. **Khởi động JVM mới:** không dựa vào việc sửa file hoặc gọi setter trong một tiến trình đã thực hiện lookup.
7. **Đọc lại security properties:** dùng `Security.getProperty` trong chính tiến trình.
8. **Kiểm thử lookup:** dùng hostname fixture và resolver có thể quan sát; kiểm soát cache OS/DNS nếu cần đo backend.
9. **Ghi nhận cấu hình:** lưu runtime identity, giá trị hai TTL, nguồn file và thời điểm khởi động cùng release.

## 10. Những lỗi cấu hình thường gặp

| Cách làm | Vì sao sai hoặc rủi ro | Cách làm đúng |
|---|---|---|
| `-Dnetworkaddress.cache.ttl=30` | Chỉ tạo System Property | Đặt trong security properties file hoặc dùng `Security.setProperty` sớm |
| `System.setProperty("networkaddress.cache.ttl", "30")` | Ghi sai namespace | Dùng `Security.setProperty` |
| Gọi `Security.setProperty` sau khi đã lookup | Cache policy có thể đã khởi tạo và không đọc lại | Đặt trước lookup đầu hoặc cấu hình file lúc startup |
| Chỉ kiểm tra `System.getProperty` | Không đọc giá trị security property | Dùng `Security.getProperty` |
| Sửa file security properties nhưng không restart | JVM đang chạy không tự nạp lại cấu hình | Khởi động tiến trình mới |
| Dùng `java.security.properties==` cho file chỉ có hai TTL | Thay toàn bộ master security properties, có thể mất cấu hình khác | Dùng một dấu `=` để nạp bổ sung |
| Dùng property nội bộ `sun.net.inetaddr.*` | Không phải cấu hình công khai, ổn định cho ứng dụng | Chỉ dùng hai security properties được tài liệu hóa |
| Dùng reflection để sửa cache private | Phụ thuộc implementation và có thể hỏng giữa các JDK | Cấu hình trước startup hoặc chạy JVM mới |

## 11. Bài tập tự kiểm tra

1. Vì sao `networkaddress.cache.ttl` là Security Property thay vì System Property?
2. `-Dnetworkaddress.cache.ttl=30` tạo ra điều gì, và vì sao nó không đổi address cache?
3. `Security.setProperty` cần được gọi trước ranh giới nào?
4. Vì sao một ứng dụng có thể đã dùng resolver trước khi vào `main` hoặc trước đoạn bootstrap của bạn?
5. `-Djava.security.properties=file:/...` khác `-Dnetworkaddress.cache.ttl=30` như thế nào?
6. Một dấu bằng và hai dấu bằng trong `java.security.properties` có ý nghĩa gì?
7. Vì sao `Security.getProperty` sau khi setter chạy chưa đủ chứng minh cache policy đã cập nhật?
8. Vì sao cấu hình file lúc khởi động thường ổn định hơn setter trong ứng dụng server?
9. Khi sửa security properties file, tại sao nên chạy một JVM mới để kiểm chứng?

**Tiêu chí hoàn thành:** Bạn phân biệt được hai namespace property, cấu hình đúng hai TTL bằng Security Properties, đặt cấu hình trước lần phân giải đầu tiên và kiểm tra được file/runtime mà ứng dụng thực sự sử dụng.

## 12. Tài liệu chuẩn

- [Networking Properties — Java SE 18](https://docs.oracle.com/en/java/javase/18/docs/api/java.base/java/net/doc-files/net-properties.html): xác nhận hai TTL là security properties và không được đặt bằng `-D` hoặc `System.setProperty`.
- [InetAddress — Java SE 18 API](https://docs.oracle.com/en/java/javase/18/docs/api/java.base/java/net/InetAddress.html): cache kết quả phân giải thành công và thất bại, cùng hai security properties điều khiển TTL.
- [Networking Properties — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/doc-files/net-properties.html): hợp đồng security properties cho address cache trên JDK hiện đại.
- [The Security Properties File — Java SE 26](https://docs.oracle.com/en/java/javase/26/security/security-properties-file.html): file master, file bổ sung và cơ chế nạp security properties.
- [Security — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/Security.html): API `Security.getProperty` và `Security.setProperty`.
