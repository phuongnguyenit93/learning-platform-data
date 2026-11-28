
# networkaddress.cache.ttl và networkaddress.cache.negative.ttl: đọc hợp đồng trên JDK đang dùng

> **Chương:** Hợp đồng `InetAddress` — **mô-đun:** `JAVA_VERSION_JAVA18`. Bài học hướng dẫn xác định JDK thực sự đang chạy, đọc hai security properties điều khiển positive/negative cache và đối chiếu mặc định theo đúng vendor, phiên bản, build. Nội dung phân biệt hợp đồng Java SE với tài liệu triển khai cụ thể; các ví dụ dùng API và cơ chế còn áp dụng trên JDK hiện đại.

Khi một ứng dụng gọi `InetAddress.getByName(host)`, JVM có thể dùng lại kết quả lookup đã lưu. Hai thuộc tính quan trọng là `networkaddress.cache.ttl` cho kết quả thành công và `networkaddress.cache.negative.ttl` cho kết quả thất bại. Cả hai là **Java Security Properties**, không phải system properties thông thường.

Đọc hợp đồng trên JDK đang dùng không chỉ là tra một con số trong tài liệu. Cần xác định đúng executable, vendor, phiên bản và build; đọc security properties thực tế; hiểu mặc định nếu property không được đặt; rồi kiểm thử trong một JVM mới. Nếu bỏ qua các bước này, con số TTL trong tài liệu có thể không phải giá trị mà tiến trình đang áp dụng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt positive cache và negative cache trong `InetAddress`.
2. Đọc đúng ý nghĩa của giá trị dương, `0` và số âm.
3. Phân biệt mặc định Java SE với mặc định cụ thể của JDK vendor/build.
4. Xác định JDK executable và runtime mà ứng dụng thực sự sử dụng.
5. Đọc hai TTL bằng `Security.getProperty` và tùy chọn chẩn đoán của JVM.
6. Cấu hình security properties qua file được nạp lúc khởi động.
7. Kiểm thử hành vi mà không nhầm cache JVM với cache hệ điều hành hoặc DNS.

## 2. Hai TTL điều khiển hai loại kết quả

`InetAddress` cache cả kết quả phân giải tên thành công và thất bại:

| Security property | Loại cache | Nội dung được giữ |
|---|---|---|
| `networkaddress.cache.ttl` | Positive cache | Một hoặc nhiều địa chỉ IP tìm được từ hostname |
| `networkaddress.cache.negative.ttl` | Negative cache | Kết quả lookup hostname thất bại |

Ví dụ minh họa:

```text
api.example.test -> 192.0.2.10
                    positive cache

missing.example.test -> UnknownHostException
                        negative cache
```

`192.0.2.0/24` là dải IPv4 dành cho tài liệu, không phải địa chỉ dịch vụ Internet có thể kết nối.

Hai TTL áp dụng cho cache trong tiến trình JVM. Chúng không đặt TTL cho bản ghi DNS authoritative, không xóa cache DNS recursive resolver và không điều khiển cache của hệ điều hành.

## 3. Đọc giá trị theo hợp đồng

### 3.1. Positive cache: networkaddress.cache.ttl

Thuộc tính `networkaddress.cache.ttl` quy định số giây giữ kết quả phân giải thành công:

| Giá trị | Hợp đồng |
|---:|---|
| Số nguyên dương, ví dụ `30` | Cache kết quả thành công trong số giây tương ứng |
| `0` | Không cache kết quả thành công trong cache `InetAddress` |
| Số âm, ví dụ `-1` | Cache kết quả thành công vô hạn |

**Mặc định positive TTL của Java SE là implementation-specific trong trường hợp hiện đại không có Security Manager.** Java SE không cam kết mọi JDK phải dùng 30 giây hoặc một con số cố định khác. JDK vendor có thể công bố mặc định riêng trong tài liệu của bản phân phối.

Ví dụ, Oracle Core Libraries Developer Guide cho Oracle JDK 25 liệt kê positive TTL mặc định là 30 giây. Con số này mô tả JDK/tài liệu Oracle tương ứng; không được suy rộng thành quy tắc cho mọi OpenJDK build hoặc vendor khác.

### 3.2. Negative cache: networkaddress.cache.negative.ttl

Thuộc tính `networkaddress.cache.negative.ttl` quy định số giây giữ kết quả lookup thất bại:

| Giá trị | Hợp đồng |
|---:|---|
| Số nguyên dương, ví dụ `5` | Cache kết quả thất bại trong số giây tương ứng |
| `0` | Không cache kết quả thất bại |
| Số âm, ví dụ `-1` | Cache kết quả thất bại vô hạn |

Java SE 18 và tài liệu Java SE hiện hành mô tả mặc định negative TTL là **10 giây**. Nếu không có cấu hình thay thế, đây là mặc định được tài liệu hóa cho property này.

Negative cache hữu ích khi một tên không tồn tại hoặc resolver tạm thời không trả địa chỉ. Nhưng nếu hostname vừa được tạo hoặc DNS vừa được sửa, entry lỗi còn hiệu lực có thể khiến ứng dụng tiếp tục nhận `UnknownHostException` cho đến khi hết thời gian cache.

### 3.3. Phân biệt 0 với số âm

| Cấu hình | Hệ quả |
|---|---|
| `networkaddress.cache.ttl=0` | Không giữ kết quả thành công trong positive cache JVM |
| `networkaddress.cache.ttl=-1` | Giữ kết quả thành công vô hạn |
| `networkaddress.cache.negative.ttl=0` | Không giữ kết quả thất bại trong negative cache JVM |
| `networkaddress.cache.negative.ttl=-1` | Giữ kết quả thất bại vô hạn |

“Không cache” chỉ nói về cache `InetAddress`. Resolver hệ điều hành, DNS recursive resolver, proxy hoặc resolver provider tùy biến vẫn có thể cache kết quả. TTL bằng `0` không bảo đảm mỗi lời gọi Java đều phát một truy vấn DNS mới ra mạng.

## 4. Java SE default và JDK vendor default

Không trộn ba lớp tài liệu sau:

| Nguồn | Câu hỏi được trả lời |
|---|---|
| Java SE API/Javadoc | Hợp đồng mà mọi implementation Java SE phải tuân thủ |
| Java SE Networking Properties | Ý nghĩa, đơn vị, giá trị đặc biệt và mặc định theo đặc tả |
| Core Libraries Guide của vendor | Mặc định/cấu hình được vendor công bố cho JDK của họ |

Ví dụ khi đối chiếu:

- Java SE 18 mô tả positive TTL là implementation-specific khi không có Security Manager; negative TTL mặc định 10 giây.
- Java SE hiện hành tiếp tục mô tả positive TTL là implementation-specific và negative TTL mặc định 10 giây.
- Oracle JDK 25 Core Libraries Guide liệt kê 30 giây cho positive TTL và 10 giây cho negative TTL.

Javadoc API mô tả hợp đồng Java SE. Hướng dẫn Core Libraries của nhà cung cấp có thể mô tả mặc định cụ thể cho JDK mà họ phát hành. Hai mức tài liệu trả lời hai câu hỏi khác nhau; hãy dùng tài liệu của đúng vendor/build khi cần biết mặc định thực tế.

Một số tài liệu cũ còn mô tả nhánh positive cache vô hạn khi Security Manager được cài đặt. Security Manager đã bị vô hiệu hóa vĩnh viễn từ JDK 24. Không dùng nhánh lịch sử đó làm hướng dẫn cấu hình cho JDK hiện đại; khi phải hỗ trợ runtime cũ, đối chiếu đúng tài liệu của runtime đó.

**Quy tắc:** nếu tài liệu Java SE ghi “implementation-specific”, hãy kiểm tra tài liệu vendor và cấu hình runtime. Không tự thay cụm từ đó bằng một con số đoán được.

## 5. Xác định JDK mà ứng dụng thực sự dùng

Máy có thể cài nhiều JDK; terminal, IDE, service wrapper, container và script triển khai có thể gọi các executable khác nhau.

### 5.1. Kiểm tra từ terminal

Trên Windows:

```powershell
java -version
where.exe java
```

Trên Linux/macOS:

```sh
java -version
command -v java
```

Kết quả `java -version` cho biết phiên bản và thường có thông tin vendor/build. Nhưng nếu ứng dụng được khởi chạy bởi IDE, service manager hoặc container, hãy kiểm tra cấu hình khởi chạy thực tế; lệnh `java` trong terminal có thể trỏ tới JDK khác.

### 5.2. In thông tin từ chính tiến trình ứng dụng

Tạo `RuntimeIdentity.java`:

```java
public class RuntimeIdentity {
    public static void main(String[] args) {
        System.out.println("java.version          = " +
                System.getProperty("java.version"));
        System.out.println("java.runtime.version  = " +
                System.getProperty("java.runtime.version"));
        System.out.println("java.vendor           = " +
                System.getProperty("java.vendor"));
        System.out.println("java.vm.name          = " +
                System.getProperty("java.vm.name"));
        System.out.println("java.vm.version       = " +
                System.getProperty("java.vm.version"));
        System.out.println("java.home             = " +
                System.getProperty("java.home"));
        System.out.println("Runtime.version       = " +
                Runtime.version());
    }
}
```

Chạy bằng đúng launcher của ứng dụng:

```text
java RuntimeIdentity.java
```

Khi ghi nhận TTL để chẩn đoán production, lưu kèm vendor, runtime version, VM version và `java.home`. Chỉ ghi “Java 25” thường chưa đủ để tái lập hành vi giữa các build hoặc nhà cung cấp.

## 6. Đọc Security Properties, không đọc nhầm System Properties

Hai TTL thuộc security policy. Các cách sau **không** cấu hình chúng:

```text
java -Dnetworkaddress.cache.ttl=30 MyApp
```

```java
System.setProperty("networkaddress.cache.ttl", "30");
```

`-D` đặt system property; `System.setProperty` thay đổi system properties. Cả hai không thay thế cơ chế Java Security Properties của hai TTL.

### 6.1. Dùng Security.getProperty

Tạo `ShowAddressCacheProperties.java`:

```java
import java.security.Security;

public class ShowAddressCacheProperties {
    public static void main(String[] args) {
        print("networkaddress.cache.ttl");
        print("networkaddress.cache.negative.ttl");
    }

    private static void print(String key) {
        String value = Security.getProperty(key);
        System.out.printf("%s = %s%n", key,
                value == null ? "<not explicitly set>" : value);
    }
}
```

Chạy:

```text
java ShowAddressCacheProperties.java
```

`Security.getProperty` trả về giá trị security property hoặc `null` nếu không có property mang khóa đó trong cấu hình đang đọc. `null` **không có nghĩa TTL bằng 0** và cũng không chứng minh cache đã tắt. JDK có thể áp dụng mặc định của implementation khi property không được đặt tường minh.

`Security.getProperty` cho biết giá trị được cấu hình, nhưng không có API công khai chung để hỏi trực tiếp “cache entry hiện tại còn sống bao nhiêu giây” hoặc ép mọi implementation công bố một default số học.

### 6.2. Dùng tùy chọn chẩn đoán JVM

Trên JDK hỗ trợ, chạy:

```text
java -XshowSettings:security -version
```

Tìm hai khóa `networkaddress.cache.ttl` và `networkaddress.cache.negative.ttl` trong phần security properties. Tùy JDK/build, lệnh có thể hiển thị nhiều thông tin hơn các giá trị cần xem; lưu output cùng thông tin runtime.

`-XshowSettings` là tùy chọn chẩn đoán của JVM, không phải API Java SE để ứng dụng truy vấn. Nếu implementation không hỗ trợ tùy chọn này, dùng `Security.getProperty` và tài liệu vendor.

### 6.3. Debug quá trình nạp security properties

JDK có thể in thông tin nạp security properties bằng:

```text
java -Djava.security.debug=properties MyApp
```

Log này hữu ích khi cần biết file nào được nạp và giá trị cuối cùng được đọc. Nó có thể dài và chứa thông tin cấu hình bảo mật khác; chỉ bật trong môi trường chẩn đoán phù hợp.

## 7. Xác định file cấu hình thực tế

### 7.1. File master

Với JDK hiện đại, file security properties chính thường nằm tại:

```text
$JAVA_HOME/conf/security/java.security
```

Trong ứng dụng, `java.home` là điểm bắt đầu để xác định thư mục runtime. Kiểm tra đúng file thuộc runtime đã in ở mục 5; đừng chỉnh file của JDK khác chỉ vì đó là JDK mặc định trong terminal.

Tìm hai khóa:

```properties
networkaddress.cache.ttl
networkaddress.cache.negative.ttl
```

Nếu một khóa không được đặt tường minh, hãy đọc phần mặc định trong tài liệu của đúng vendor/build. Không tự chuyển giá trị thiếu thành `0`.

### 7.2. File bổ sung qua java.security.properties

Có thể tạo file riêng, ví dụ `inetaddress-cache.properties`:

```properties
networkaddress.cache.ttl=30
networkaddress.cache.negative.ttl=5
```

Nạp file bổ sung khi khởi động:

```text
java -Djava.security.properties=file:/absolute/path/inetaddress-cache.properties MyApp
```

Trên Windows, dùng file URI hợp lệ, ví dụ:

```text
java -Djava.security.properties=file:///C:/config/inetaddress-cache.properties MyApp
```

Một dấu `=` có nghĩa nạp file security properties bổ sung vào cấu hình master. Dạng hai dấu `==` thay thế toàn bộ master security properties file:

```text
java -Djava.security.properties==file:/absolute/path/custom-security.properties MyApp
```

Không dùng dạng thay thế toàn bộ chỉ để đặt hai TTL nếu file custom không chứa các security settings còn lại mà JDK cần. Với cấu hình TTL riêng, file bổ sung bằng một dấu bằng thường dễ kiểm soát hơn.

### 7.3. Có thể đặt bằng Security.setProperty không?

`Security.setProperty(key, value)` là API đặt một security property trong tiến trình. Tuy nhiên, chính sách cache của `InetAddress` có thể đã được đọc khi lớp networking khởi tạo. Nếu thay đổi sau thời điểm đó, lời gọi có thể không đổi hành vi đang dùng; API không nhất thiết ném ngoại lệ để báo việc thay đổi đã quá muộn.

Vì vậy:

1. Ưu tiên cấu hình file trước khi JVM khởi động.
2. Nếu đặt bằng `Security.setProperty` trong bootstrap, thực hiện trước lần phân giải hostname đầu tiên.
3. Không thay đổi TTL giữa các request và kỳ vọng cache entry đã tạo được viết lại theo chính sách mới.
4. Khi cần so sánh hai chính sách, khởi chạy hai tiến trình JVM riêng với cấu hình riêng.

## 8. TTL của InetAddress khác TTL của DNS

Không đồng nhất các lớp cache:

| TTL/cache | Chủ thể điều khiển | Phạm vi |
|---|---|---|
| `networkaddress.cache.ttl` | Security properties của JVM | Cache kết quả thành công trong tiến trình Java |
| `networkaddress.cache.negative.ttl` | Security properties của JVM | Cache kết quả lookup thất bại trong tiến trình Java |
| DNS record TTL | Chủ sở hữu vùng DNS | Thời gian resolver DNS được hướng dẫn cache bản ghi |
| OS/resolver cache | Hệ điều hành hoặc dịch vụ resolver | Cache ở cấp máy hoặc network namespace |
| Proxy/client cache | HTTP client, proxy hoặc service mesh | Chính sách riêng của thành phần đó |

Ví dụ: DNS authoritative đổi địa chỉ từ `192.0.2.10` sang `192.0.2.20`. Nếu JVM còn positive cache entry, ứng dụng có thể tiếp tục nhận địa chỉ cũ cho tới khi cache JVM hết hạn. Ngược lại, nếu JVM không cache nhưng resolver hệ điều hành vẫn giữ dữ liệu cũ, lần lookup mới từ Java vẫn có thể nhận địa chỉ cũ.

Khi hostname vừa được thêm vào DNS, negative cache của JVM có thể giữ lỗi cũ trong một khoảng thời gian. `networkaddress.cache.negative.ttl=0` chỉ bỏ cache âm ở JVM; nó không xóa negative cache của DNS recursive resolver hoặc OS.

## 9. Cache ảnh hưởng resolver provider như thế nào?

Từ Java 18, `InetAddressResolverProvider` có thể cung cấp resolver tùy biến. Cache của `InetAddress` ảnh hưởng số lần resolver được gọi:

| Lần gọi | Trạng thái | Provider có thể được gọi? |
|---|---|---|
| Lookup hostname đầu tiên, cache miss | Chưa có entry | Có |
| Lookup lặp trong positive TTL | Positive cache hit | Không cần gọi lại |
| Lookup lặp trong negative TTL | Negative cache hit | Không cần gọi lại |
| Lookup sau khi entry hết hạn | Cần refresh | Có thể được gọi lại |

Nếu provider ghi log hoặc đếm số lần `lookupByName` được gọi, số lần đó có thể thấp hơn số lần ứng dụng gọi `InetAddress.getByName` hoặc `getAllByName`. Reverse lookup cũng có cache; không chỉ forward lookup mới chịu ảnh hưởng.

## 10. Kiểm thử và chẩn đoán đúng

### 10.1. Ma trận kiểm thử

| Cấu hình | Kịch bản | Điều cần quan sát |
|---|---|---|
| Positive TTL `0` | Phân giải cùng hostname nhiều lần | Cache JVM không giữ positive result giữa các lần lookup |
| Positive TTL `30` | Lookup lặp trong cửa sổ 30 giây | Kết quả có thể được trả từ positive cache JVM |
| Negative TTL `0` | Lookup hostname thử nghiệm thất bại lặp lại | Cache JVM không giữ negative result |
| Negative TTL `5` | Lookup thất bại rồi thử lại trong 5 giây | Kết quả lỗi có thể được trả từ negative cache |

Mỗi cấu hình nên chạy trong tiến trình JVM mới. Dùng hostname fixture do bạn kiểm soát; tránh phụ thuộc DNS công cộng hoặc một IP cụ thể không ổn định.

### 10.2. Đo thời gian không đủ chứng minh cache

Lần gọi thứ hai nhanh hơn lần đầu không chứng minh chắc chắn `InetAddress` cache đã hit. Cache của hệ điều hành, DNS recursive resolver, resolver provider, JIT warm-up và tải hệ thống cũng có thể làm thời gian khác nhau.

Nếu cần xác minh số lần resolver được gọi, dùng `InetAddressResolverProvider` thử nghiệm có bộ đếm và hostname fixture riêng. So sánh số lần ứng dụng gọi `InetAddress` với số lần `lookupByName` thực sự chạy; cache JVM có thể khiến hai con số khác nhau.

### 10.3. Không có API công khai để xóa tùy ý cache InetAddress

`InetAddress` không cung cấp API công khai chung để xóa một cache entry cụ thể. Khi cần trạng thái sạch, dùng JVM mới, cấu hình trước lookup đầu tiên và kiểm soát cache ở lớp resolver/OS nếu bài test yêu cầu.

Không dùng reflection để sửa cache private và không dùng các cờ nội bộ `sun.net.inetaddr.ttl` hoặc `sun.net.inetaddr.negative.ttl` làm cấu hình sản phẩm. Chúng không phải security properties chuẩn mà ứng dụng nên dựa vào.

### 10.4. Checklist khi kết quả khác mong đợi

1. Xác nhận đúng JDK vendor, phiên bản và build đang chạy.
2. Đọc Security Properties, không chỉ đọc system properties.
3. Kiểm tra file `java.security` master và file bổ sung được nạp qua `java.security.properties`.
4. Xác nhận giá trị là số giây, và phân biệt `0` với số âm.
5. Kiểm tra ứng dụng đã lookup hostname trước khi cấu hình được áp dụng hay chưa.
6. Kiểm tra cache OS, DNS resolver hoặc provider tùy biến.
7. Dùng JVM mới để lặp lại kịch bản có kiểm soát.

## 11. Lựa chọn TTL theo yêu cầu vận hành

| Nhu cầu | Hướng cân nhắc | Rủi ro cần đánh giá |
|---|---|---|
| Endpoint ổn định, ít thay đổi | Positive TTL dài hơn | Địa chỉ cũ có thể được giữ sau khi thay đổi khẩn cấp |
| Endpoint thay đổi thường xuyên | Positive TTL hữu hạn, ngắn hơn | Lookup tăng và phụ thuộc resolver nhiều hơn |
| Hostname thường được tạo sau khi ứng dụng khởi động | Negative TTL hữu hạn, ngắn | Tránh giữ lỗi lâu sau khi tên đã xuất hiện |
| Resolver dễ bị lỗi tạm thời | Negative TTL vừa phải | TTL quá ngắn làm tăng lookup lặp; TTL quá dài giữ lỗi |
| Cần failover nhanh | TTL phù hợp SLA và chiến lược thử lại nhiều địa chỉ | TTL không thay thế logic kết nối dự phòng |

Không có một bộ TTL tối ưu cho mọi dịch vụ. Hãy cân bằng tốc độ cập nhật endpoint, khả năng chịu lỗi resolver, tải DNS, chi phí lookup và rủi ro dùng địa chỉ đã cũ.

## 12. Quy trình đọc hợp đồng cho một runtime

Khi tiếp nhận một ứng dụng Java và cần xác định TTL thực tế, làm theo thứ tự:

1. **Xác định runtime:** lấy `java.vendor`, `java.runtime.version`, `java.vm.version` và `java.home` từ chính tiến trình ứng dụng.
2. **Đọc security properties:** dùng `-XshowSettings:security` hoặc `Security.getProperty`.
3. **Đối chiếu file:** kiểm tra `$JAVA_HOME/conf/security/java.security` và file bổ sung được nạp bằng `java.security.properties`.
4. **Đối chiếu tài liệu:** đọc Java SE Networking Properties, sau đó đọc Core Libraries Guide của đúng vendor/version.
5. **Diễn giải default:** nếu positive TTL không được đặt và Java SE nói implementation-specific, không đoán giá trị; tìm tài liệu của vendor/build.
6. **Kiểm thử:** dùng hostname fixture và tiến trình JVM mới để kiểm chứng cache theo cấu hình.
7. **Ghi nhận:** lưu runtime identity, hai giá trị security property, nguồn cấu hình và thời điểm thu thập.

Một bản ghi chẩn đoán nên có dạng:

```text
Vendor:
Runtime version:
VM version:
java.home:
networkaddress.cache.ttl:
networkaddress.cache.negative.ttl:
Security properties source:
Collected at:
```

Không ghi “TTL mặc định của Java” nếu chưa nêu vendor/version và nguồn tài liệu.

## 13. Bài tập tự kiểm tra

1. Vì sao Java SE không bảo đảm một giá trị positive TTL giống nhau trên mọi implementation?
2. Negative TTL mặc định được tài liệu Java SE mô tả là bao nhiêu?
3. Vì sao Oracle JDK 25 guide có thể liệt kê 30 giây mà không biến 30 giây thành hợp đồng cho mọi JDK?
4. `Security.getProperty` trả `null` có nghĩa cache bị tắt không?
5. Vì sao `-Dnetworkaddress.cache.ttl=30` không phải cấu hình đúng?
6. Lệnh nào giúp xem security properties của runtime đang khởi chạy?
7. Một dấu bằng và hai dấu bằng trong `java.security.properties` khác nhau thế nào?
8. Vì sao cần dùng JVM mới khi so sánh hai TTL?
9. Vì sao không nên dùng các property nội bộ `sun.net.inetaddr.*` trong cấu hình ứng dụng hiện đại?

**Tiêu chí hoàn thành:** Bạn có thể xác định đúng runtime, đọc hai Security Properties, giải thích mặc định theo đúng tài liệu Java SE/vendor, cấu hình qua file khởi động và chứng minh hành vi bằng một phép thử có kiểm soát.

## 14. Tài liệu chuẩn

- [Networking Properties — Java SE 18](https://docs.oracle.com/en/java/javase/18/docs/api/java.base/java/net/doc-files/net-properties.html): hợp đồng positive/negative TTL trong baseline Java 18.
- [InetAddress — Java SE 18 API](https://docs.oracle.com/en/java/javase/18/docs/api/java.base/java/net/InetAddress.html): cache thành công và thất bại trong API `InetAddress`.
- [Networking Properties — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/doc-files/net-properties.html): hợp đồng hiện hành, giá trị âm/0 và mặc định implementation-specific.
- [InetAddress — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/InetAddress.html): mô tả cache lookup thành công và thất bại.
- [Core Libraries Developer Guide — Oracle JDK 25](https://docs.oracle.com/en/java/javase/25/core/java-core-libraries-developer-guide.pdf): bảng Address Cache Properties và mặc định cụ thể của Oracle JDK 25.
- [The Security Properties File — Java SE 26](https://docs.oracle.com/en/java/javase/26/security/security-properties-file.html): file master, file bổ sung và giới hạn thay đổi security properties khi runtime đã khởi tạo.
- [The java Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html): cú pháp `-XshowSettings:security` và các nhóm settings.
- [The Security Manager Is Permanently Disabled — JDK 24](https://docs.oracle.com/en/java/javase/24/security/security-manager-is-permanently-disabled.html): thay đổi từ JDK 24, giúp đọc đúng các ghi chú lịch sử trong tài liệu cũ.
