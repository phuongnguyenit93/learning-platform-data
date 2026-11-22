# Phạm vi phân tích mã nguồn, bytecode và cấu hình

Khi một pipeline báo **“static analysis passed”**, thông báo đó chưa đủ để kết luận ứng dụng an toàn hoặc hoạt động đúng. Công cụ có thể chỉ kiểm tra cách đặt tên trong các tệp Java, phân tích những lớp **.class** đã biên dịch, hoặc quét cấu hình để phát hiện một số thiết lập nguy hiểm. Mỗi cách nhìn thấy **một phần khác nhau của hệ thống** và cũng có những điều không thể quan sát.

Trong chương **Kiểm tra tự động** của module **CODE_QUALITY_FUNDAMENTALS**, mục tiêu là hiểu cách các thuộc tính của mã nguồn ảnh hưởng tới độ tin cậy, khả năng đọc và khả năng thay đổi. Vì vậy, khi sử dụng công cụ tự động, cần biết **đối tượng được kiểm tra**, **loại lỗi có khả năng phát hiện**, **phần không được kiểm tra** và **cách diễn giải bằng chứng**. Bài này tập trung vào ba phạm vi quan trọng: **mã nguồn**, **bytecode** và **cấu hình**.

> Một kết quả kiểm tra chỉ có ý nghĩa khi đi kèm phạm vi: công cụ đọc cái gì, áp dụng quy tắc nào, ở phiên bản nào, và đã bỏ qua những phần nào?

## 1. Ba dạng đầu vào, ba góc nhìn

Trong một dự án Java thông thường, các công cụ có thể được đặt ở những điểm khác nhau:

~~~text
                  Repository
                      |
          +-----------+-----------+
          |                       |
          v                       v
    Tệp nguồn Java         Tệp cấu hình / build
   (.java, source AST)    (.yml, .properties,
          |               build.gradle, pom.xml,
          v               Dockerfile, IaC, ...)
   Biên dịch + xử lý             |
   annotation/generate          v
          |                Quét cấu hình,
          v                phụ thuộc, chính sách
    Bytecode JVM
   (.class, .jar)
          |
          v
    Chạy với JVM,
    thư viện, dữ liệu,
    hạ tầng thực tế
~~~

Các lớp kiểm tra không nhất thiết chạy theo đúng thứ tự trên; một số công cụ nguồn chạy trong quá trình biên dịch, còn quét cấu hình có thể diễn ra trước hoặc sau build. Sơ đồ thể hiện **những dạng dữ liệu được quan sát**, không quy định một pipeline duy nhất.

| Phạm vi | Đầu vào tiêu biểu | Phù hợp để kiểm tra | Không trực tiếp kết luận được |
| --- | --- | --- | --- |
| **Mã nguồn** | Tệp **.java**, cú pháp và cây cú pháp trừu tượng (**AST**) | Tên, định dạng, cấu trúc mã, một số mẫu lỗi và quy tắc phụ thuộc | Mọi bytecode cuối cùng, hành vi với môi trường thật |
| **Bytecode** | Tệp **.class**, thư viện **.jar**, classpath cần thiết | Một số luồng dữ liệu và thao tác JVM sau biên dịch; mẫu lỗi và lời gọi API | Bình luận, cách xuống dòng, toàn bộ ngữ nghĩa nghiệp vụ |
| **Cấu hình** | YAML, properties, build scripts, manifest, khai báo phụ thuộc | Các tùy chọn, quyền, cấu hình rủi ro, dependency và chính sách build | Giá trị runtime chưa được cung cấp, kết quả tích hợp thật |

Cả ba là **phân tích tĩnh** nếu công cụ chỉ đọc đầu vào và suy luận mà không chạy phần mềm theo các tình huống nghiệp vụ. Để quan sát kết quả thật, thường cần **kiểm thử động**, kiểm thử tích hợp hoặc giám sát khi vận hành.

## 2. Phân tích mã nguồn kiểm tra được những gì?

**Phân tích mã nguồn** đọc văn bản lập trình hoặc cấu trúc được trích ra từ văn bản đó. Với Java, công cụ có thể hoạt động ở những mức khác nhau:

- **Mức văn bản và token:** kiểm tra khoảng trắng, độ dài dòng, quy ước đặt tên, import.
- **Mức AST:** hiểu cấu trúc class, phương thức, biểu thức, nhánh **if**, **switch**, **try**.
- **Mức ngữ nghĩa có thông tin kiểu:** tra cứu kiểu, chữ ký phương thức, lời gọi và quan hệ dữ liệu với sự hỗ trợ của compiler hoặc bộ phân giải kiểu.
- **Mức luồng điều khiển/luồng dữ liệu:** suy luận một giá trị có thể là null, có thể không được đóng hoặc có thể đi tới điểm sử dụng nhạy cảm.

Không nên gộp các mức này thành “công cụ đọc source nên tự hiểu mọi hành vi”. Công cụ khác nhau có mức hiểu cú pháp, kiểu và đường đi dữ liệu rất khác nhau.

### 2.1. Quy ước và khả năng đọc

Giả sử dự án có quy ước đặt tên hằng số như sau:

~~~java
public final class ShippingSettings {
    private static final long standardFeeVnd = 30_000L;
}
~~~

Một quy tắc đặt tên có thể yêu cầu hằng số kiểu này dùng **UPPER_SNAKE_CASE**, chẳng hạn:

~~~java
public final class ShippingSettings {
    public static final long STANDARD_FEE_VND = 30_000L;

    private ShippingSettings() {}
}
~~~

Với ví dụ sau, chỉ riêng văn bản nguồn đã cho công cụ đủ dữ liệu để phát hiện một số vi phạm định dạng hoặc tên gọi. Nhưng tên đẹp **không chứng minh** phí vận chuyển 30.000 VND là chính sách đúng.

Các công cụ phân tích nguồn có thể thuộc nhóm kiểm tra phong cách như **Checkstyle**, hoặc cung cấp thêm phân tích cấu trúc, mẫu lỗi như **PMD**. Khả năng chính xác phải được kiểm tra theo phiên bản công cụ, bộ rule và cấu hình đang sử dụng.

### 2.2. Nhánh điều khiển và lỗi có thể suy luận

~~~java
public final class CustomerCode {
    public static int length(String code) {
        if (code == null) {
            return code.length();
        }
        return code.length();
    }
}
~~~

Trong nhánh **code == null**, lệnh **code.length()** chắc chắn gây **NullPointerException** khi được thực thi. Một bộ phân tích có hiểu luồng điều khiển và quan hệ null có thể cảnh báo lỗi này ngay khi chưa có kiểm thử cụ thể.

Tuy nhiên, không phải mọi công cụ phân tích source đều có khả năng suy luận null như nhau. Một linter chỉ kiểm tra định dạng sẽ không phát hiện vì mã vẫn đúng phong cách. Một công cụ phân tích sâu có thể phát hiện nhiều mẫu null khác, nhưng cũng có giới hạn về thư viện, alias, phản xạ và các đường đi phức tạp.

### 2.3. Lỗi nghiệp vụ khó nhận ra bằng quy tắc cú pháp

~~~java
public static boolean getsFreeShipping(long subtotalVnd) {
    return subtotalVnd > 500_000L;
}
~~~

Nếu hợp đồng nghiệp vụ quy định **“từ 500.000 VND trở lên”**, điều kiện **>** là sai tại đúng ngưỡng. Mã có thể hoàn toàn hợp lệ về cú pháp, tên và kiểu. Công cụ tĩnh không có hợp đồng nghiệp vụ sẽ khó biết phải dùng **>=**.

Để có bằng chứng cho lỗi này, cần **kiểm thử dựa trên yêu cầu**, ví dụ:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;
import org.junit.jupiter.api.Test;

class ShippingRuleTest {
    @Test
    void freeShippingStartsAtThreshold() {
        assertTrue(ShippingRules.getsFreeShipping(500_000L));
    }
}
~~~

**ShippingRules** trong ca kiểm thử là thành phần minh họa chứa quy tắc đang được kiểm tra. Trường hợp này cho thấy phân tích mã nguồn giúp tìm nhiều lỗi cấu trúc, nhưng **không thay thế oracle nghiệp vụ**.

## 3. Bytecode là gì và vì sao kiểm tra ở mức bytecode?

Với Java, trình biên dịch **javac** chuyển mã nguồn thành các tệp **.class** chứa **JVM bytecode**, metadata và các thông tin khác tùy cách build. Bytecode là dạng mà JVM có thể tải và thực thi theo hợp đồng của nền tảng.

Một phân tích bytecode thường xem:

- Các lớp, phương thức và trường thực sự có mặt sau biên dịch.
- Lệnh JVM, lời gọi phương thức, thao tác với đối tượng và giá trị.
- Đường điều khiển ở mức bytecode, vị trí xử lý ngoại lệ.
- Một số annotation và metadata được lưu trong class file.
- Quan hệ tới thư viện nếu classpath đủ để công cụ suy luận.

Ví dụ, với phương thức:

~~~java
public static long totalVnd(long unitPriceVnd, int quantity) {
    return Math.multiplyExact(unitPriceVnd, quantity);
}
~~~

Bytecode sẽ chứa biểu diễn tương ứng của việc nhận tham số và gọi **Math.multiplyExact**. Công cụ phân tích không cần dựa vào cách đoạn mã được xuống dòng hoặc tên biến cục bộ có dễ hiểu hay không.

Một công cụ nổi tiếng trong nhóm này là **SpotBugs**: nó phân tích mã Java đã biên dịch để tìm các mẫu lỗi tiềm ẩn. Một số bộ kiểm tra khác thực hiện phân tích ngay trong compiler hoặc trên mô hình trung gian; không nên tự động coi tất cả chúng đều là “bytecode scanners”.

### 3.1. Những lỗi bytecode có thể gợi ý

Phân tích bytecode có thể giúp phát hiện những tình huống như:

- Khả năng dereference một giá trị có thể null theo luồng đã phân tích.
- Một số cách dùng so sánh, equals, hashCode hoặc lời gọi API dễ gây nhầm lẫn.
- Một số tài nguyên được tạo nhưng không được đóng trên đường đi nhất định.
- Những mẫu lỗi liên quan tới đồng thời hoặc trạng thái dùng chung.
- Một số thao tác không nhất quán giữa cách dùng kiểu và phương thức.

Đây là **khả năng phụ thuộc bộ rule và điều kiện suy luận**; không phải mọi công cụ bytecode đều phát hiện mọi loại lỗi kể trên, và cũng không phải mọi cảnh báo là lỗi chắc chắn trong ứng dụng cụ thể.

### 3.2. Khác biệt giữa source và bytecode

Đoạn Java:

~~~java
try (InputStream input = Files.newInputStream(path)) {
    return input.readAllBytes();
}
~~~

được compiler chuyển thành một chuỗi lệnh và đường xử lý ngoại lệ để đóng stream theo ngữ nghĩa **try-with-resources**. Phân tích bytecode nhìn thấy cấu trúc đã biên dịch; phân tích nguồn nhìn thấy cú pháp và mục đích được biểu đạt bởi **try-with-resources**.

Hai công cụ có thể đánh giá cùng hành vi từ các biểu diễn khác nhau:

- Công cụ nguồn có thể kiểm tra quy tắc “sử dụng try-with-resources khi mở tài nguyên”.
- Công cụ bytecode có thể suy luận những đường đi mà tài nguyên được đóng hoặc còn khả năng bị rò rỉ.
- Kiểm thử động có thể xác nhận stream thực sự được đóng trong các tình huống đã thiết lập.

Không nên tuyên bố bytecode “tốt hơn source” hoặc ngược lại. **Mỗi dạng có tín hiệu và mất mát thông tin khác nhau.**

### 3.3. Thông tin không còn ở dạng dễ quan sát

Bytecode thường không giữ nguyên:

- Khoảng trắng, cách xuống dòng và phần lớn bố cục mã nguồn.
- Bình luận giải thích quy tắc nghiệp vụ.
- Ý định đặt tên một số biến cục bộ nếu build không giữ metadata phù hợp.
- Toàn bộ cấu trúc cấp cao của source theo đúng cách người lập trình đã viết.

Thông tin dòng nguồn hoặc tên biến cục bộ **có thể được giữ** nếu cấu hình biên dịch phát ra metadata tương ứng; không nên giả định luôn có hoặc luôn bị loại bỏ.

Vì vậy, một bytecode analyzer có thể đưa ra cảnh báo đúng về đường thực thi nhưng không thể thay thế formatter hoặc đánh giá chất lượng tài liệu Javadoc.

## 4. Kiểm tra mã do compiler hoặc công cụ sinh ra

Trong một dự án Java hiện đại, mã được chạy không nhất thiết chỉ đến từ tệp **.java** do lập trình viên viết tay.

Ví dụ:

- **Annotation processor** sinh thêm lớp Java hoặc mã hỗ trợ khi biên dịch.
- Một số framework tạo proxy, bridge, accessor hoặc thành phần phụ trợ.
- Compiler có thể tạo phương thức synthetic hoặc bridge để thực hiện quy tắc ngôn ngữ.
- Một module có thể chứa thư viện viết bằng ngôn ngữ JVM khác rồi đóng gói thành **.class**.
- Plugin build có thể tạo source hoặc biến đổi bytecode trong một bước riêng.

### 4.1. Vì sao phạm vi dễ bị lệch?

~~~text
src/main/java  -----> source scanner
      |
      +--> annotation processing
                |
                v
         generated source
                |
                v
         compiled .class ------> bytecode scanner
                |
                v
         packaged application
~~~

Nếu source scanner chỉ nhận **src/main/java**, nó có thể **không nhìn thấy generated source**. Ngược lại, bytecode analyzer chạy trên thư mục class sau compilation có thể thấy nhiều lớp đã được sinh ra, tùy cách build tạo artifact và đường dẫn được quét.

Điều cần kiểm tra trong dự án thật:

1. Tệp nguồn nào được đưa vào công cụ phân tích?
2. Thư mục generated source có được tính không, và nếu có thì ai chịu trách nhiệm sửa cảnh báo?
3. Thư mục class nào được quét: main, test, integration test hay tất cả?
4. Có module hoặc JAR nào không được build/quét trong pipeline?
5. Có bước biến đổi bytecode **sau** lần phân tích không?

Một scanner chạy xanh trên một phần đầu vào **không thể chứng minh** các phần còn lại không có vấn đề.

## 5. Phân tích cấu hình: nhìn vào điều kiện vận hành và triển khai

Cấu hình cũng có thể làm một ứng dụng đúng về logic trở nên khó vận hành hoặc có rủi ro bảo mật. Ví dụ:

- Mở rộng phạm vi endpoint quản trị được expose qua HTTP.
- Bật chế độ debug hoặc logging nhạy cảm trong môi trường production.
- Dùng timeout hoặc số connection thiếu phù hợp với tải.
- Khai báo image container hoặc dependency với phiên bản không được kiểm soát.
- Cấp quyền quá rộng cho workload hoặc service account.
- Đặt thông tin bí mật trực tiếp trong tệp cấu hình được commit.

**Phân tích cấu hình** thường đọc **YAML, properties, JSON, XML, build scripts, Dockerfile, manifest hoặc Infrastructure as Code** để tìm cấu trúc và giá trị theo chính sách.

### 5.1. Ví dụ Spring Boot: lựa chọn cấu hình có ý nghĩa

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
~~~

Đây là cấu hình minh họa có thể khiến nhiều endpoint quản trị được đưa vào phạm vi exposure web, tùy phiên bản và cấu hình ứng dụng. Một rule tĩnh có thể yêu cầu xem xét việc sử dụng ký tự **"*"** vì đây là cấu hình rộng.

Tuy nhiên, **cấu hình exposure không tự chứng minh endpoint truy cập được bởi người không có quyền**. Còn cần xét cấu hình xác thực, phân quyền, network, reverse proxy, profile đang chạy và phiên bản framework.

Một cách khai báo chặt hơn, khi ứng dụng chỉ cần một tập nhỏ endpoint:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Ngay cả cấu hình này vẫn cần cân nhắc **nội dung dữ liệu được trả về**, quyền truy cập và chính sách vận hành. Công cụ quét cấu hình giúp phát hiện rủi ro từ giá trị khai báo, **không thay thế kiểm thử truy cập thực tế**.

### 5.2. Cấu hình động và profile

Một file có thể không phản ánh giá trị cuối cùng khi chạy:

~~~yaml
service:
  timeout-ms: 1500
~~~

Giá trị thực có thể đến từ biến môi trường như **SERVICE_TIMEOUT_MS**, tham số dòng lệnh hoặc cấu hình ở tầng cao hơn theo quy tắc ưu tiên của framework. Nếu scanner chỉ đọc file này, nó biết giá trị khai báo **1500**, nhưng không thể biết chắc production hiện dùng bao nhiêu nếu không có thông tin môi trường tương ứng.

Các nguồn cấu hình có thể ghi đè nhau:

- Tệp mặc định của ứng dụng.
- Tệp hoặc profile riêng theo môi trường.
- Biến môi trường và tham số dòng lệnh.
- Cấu hình được inject từ hệ thống triển khai.
- Secret manager hoặc config service ngoài repository.

Vì vậy, cần phân biệt **cấu hình khai báo trong repository** với **cấu hình hiệu lực tại runtime**. Một quy tắc có thể dùng dữ liệu runtime nếu công cụ được cung cấp, nhưng không nên giả định scanner tĩnh tự nhìn thấy mọi nguồn ghi đè.

## 6. Cấu hình build và dependency là một phạm vi riêng

Các tệp như **pom.xml**, **build.gradle**, version catalog và lockfile cho thấy cách dự án chọn thư viện, plugin, compiler option và nguồn artifact. Quét những tệp này có thể phát hiện:

- Dependency hoặc plugin có phiên bản đã biết có lỗ hổng theo cơ sở dữ liệu tư vấn của công cụ.
- Sử dụng phiên bản không xác định hoặc cơ chế resolve thiếu kiểm soát, tùy chính sách.
- Cấu hình bỏ qua test hoặc phân tích trong một số job.
- Sự khác nhau giữa dependency chính và dependency chỉ dùng cho kiểm thử.
- Những quy định về nguồn tải, checksum hoặc xác minh artifact chưa được thực hiện.

### 6.1. Phân tích thành phần phần mềm khác phân tích bytecode

**Software Composition Analysis (SCA)** thường dựa vào danh sách thư viện, phiên bản, dependency tree, lockfile hoặc **Software Bill of Materials (SBOM)**. Nó có thể báo rằng một phiên bản thư viện nằm trong danh sách có lỗ hổng đã công bố.

Điều này **không đồng nghĩa** bytecode analyzer đã chứng minh ứng dụng gọi tới đoạn mã dễ bị khai thác. Ngược lại, một bản JAR có cấu trúc bytecode “không có cảnh báo” vẫn có thể chứa thư viện với CVE đã biết.

| Phân tích | Câu hỏi chính |
| --- | --- |
| Quét **source Java** | Cách viết, lời gọi, luồng dữ liệu và cấu trúc mã có biểu hiện lỗi không? |
| Quét **bytecode JVM** | Mã đã biên dịch có mẫu lỗi hoặc đường thực thi đáng ngờ nào không? |
| **SCA/dependency scan** | Artifact hoặc dependency ở phiên bản nào, có tư vấn lỗ hổng hay vi phạm chính sách không? |
| **Configuration scan** | Các thiết lập khai báo có đáp ứng chính sách bảo mật/vận hành không? |
| **Runtime test** | Hệ thống ở môi trường đã thiết lập có hoạt động như hợp đồng không? |

Kết quả SCA còn phụ thuộc mức độ đầy đủ của cây dependency, dữ liệu tư vấn, cách ánh xạ package/version và ngữ cảnh sử dụng. Một cảnh báo có thể cần đánh giá mức độ ảnh hưởng và khả năng khai thác thực tế; **không được xóa cảnh báo chỉ vì không thấy lời gọi trực tiếp trong mã ứng dụng**.

### 6.2. Source set, scope và phần mềm được đóng gói

Một thư viện chỉ dùng cho test có thể không nằm trong sản phẩm chạy production. Một dependency được khai báo có thể không được đóng gói theo đúng cách người đọc suy đoán. Ngược lại, một JAR được đưa vào container qua bước đóng gói ngoài repository có thể không được liệt kê trong source tree.

Do đó, khi đánh giá SCA cần xác định mục tiêu:

- Kiểm tra **mọi dependency trong quá trình phát triển** hay chỉ dependency runtime?
- Kiểm tra **artifact được deploy thật** hay chỉ file khai báo?
- Có dependency bắc cầu (*transitive*) và plugin build được đưa vào không?
- Có JAR được sao chép thủ công vào image hoặc thư mục triển khai không?

Đây là câu hỏi về **phạm vi đầu vào**, không chỉ là lựa chọn công cụ.

## 7. Một lỗi có thể được phát hiện ở những lớp nào?

Xem một ví dụ truy vấn dữ liệu dùng chuỗi từ bên ngoài:

~~~java
// Minh họa cách viết cần tránh với input do client cung cấp:
String sql = "SELECT id FROM orders WHERE customer_id = '"
        + customerId + "'";
Statement statement = connection.createStatement();
ResultSet result = statement.executeQuery(sql);
~~~

Một số công cụ phân tích nguồn có khả năng theo dõi dữ liệu từ input tới SQL execution có thể cảnh báo nguy cơ injection. Một số công cụ phân tích bytecode hoặc data-flow cũng có thể phát hiện mẫu rủi ro tương ứng nếu đủ ngữ cảnh. Nhưng một linter về định dạng sẽ không phát hiện, và scanner cấu hình cũng không chứng minh câu truy vấn an toàn.

Cách viết tách dữ liệu khỏi cấu trúc:

~~~java
String sql = "SELECT id FROM orders WHERE customer_id = ?";
try (PreparedStatement query =
             connection.prepareStatement(sql)) {
    query.setString(1, customerId);
    try (ResultSet rows = query.executeQuery()) {
        while (rows.next()) {
            process(rows.getLong("id"));
        }
    }
}
~~~

**process** và các biến thuộc môi trường repository là thành phần minh họa; đoạn mã tập trung vào cơ chế bind và đóng tài nguyên. PreparedStatement giúp xử lý injection đối với **giá trị customerId**, nhưng vẫn chưa cho biết người dùng được phép xem các đơn hàng đó hay không.

| Câu hỏi review | Lớp kiểm tra có thể hỗ trợ |
| --- | --- |
| Mã ghép dữ liệu vào SQL bằng nối chuỗi? | Phân tích source/data-flow hoặc bytecode với rule phù hợp |
| Cấu trúc truy vấn có bind giá trị? | Review source, kiểm thử tích hợp và công cụ phân tích chuyên biệt |
| Tài nguyên JDBC có đường đi không đóng? | Phân tích source/bytecode, kiểm thử lỗi và giám sát pool |
| Cấu hình DB có timeout hợp lý? | Quét cấu hình và kiểm thử vận hành |
| Driver và thư viện có bản vá phù hợp? | SCA và kiểm kê artifact triển khai |
| Người gọi có được phép đọc customerId này? | Thiết kế authorization, kiểm thử quyền truy cập |
| Truy vấn có hoạt động đúng trên DB thực? | Kiểm thử tích hợp với schema và dữ liệu phù hợp |

**Kết luận:** nhiều phạm vi kiểm tra tạo bằng chứng bổ trợ, nhưng không phạm vi nào tự động bao trùm toàn bộ tính đúng đắn và bảo mật.

## 8. Giới hạn chung của phân tích tĩnh

Một phân tích tĩnh thường không thể liệt kê chính xác mọi tình huống runtime, đặc biệt khi có:

- **Reflection:** tên class hoặc phương thức được chọn động từ chuỗi.
- **Dynamic class loading/plugin:** mã mới chỉ được tải khi vận hành.
- **Dependency injection:** đối tượng thực tế phụ thuộc cấu hình hoặc profile.
- **Native method hoặc external service:** tác dụng phụ xảy ra bên ngoài phần mã đang quét.
- **Concurrency:** các lịch chạy và interleaving có thể rất lớn.
- **Dữ liệu runtime:** giá trị biến môi trường, cơ sở dữ liệu và yêu cầu người dùng không cố định.
- **Generated code và build variants:** artifact cuối có thể khác phần nguồn mà công cụ đã đọc.

Hệ quả là:

1. Có thể có **false positive**: công cụ cảnh báo một đường đi thực tế không thể xảy ra trong hợp đồng ứng dụng.
2. Có thể có **false negative**: lỗi thật không được rule nhận ra hoặc nằm ngoài phần đầu vào được quét.
3. Không có cảnh báo **không phải bằng chứng** phần mềm không có lỗi.

### 8.1. Ví dụ false positive có thể cần xem xét

Giả sử một scanner thấy giá trị null có thể truyền tới một phương thức yêu cầu không null. Nhưng ở điểm gọi, ứng dụng đã kiểm tra một bất biến mà scanner không mô hình hóa được. Đây **có thể** là false positive.

Không nên lập tức tắt cảnh báo. Cách xử lý tốt là:

- Kiểm chứng bất biến thực sự tồn tại trên mọi đường đi.
- Làm hợp đồng rõ hơn trong mã nếu khả thi, ví dụ validation hoặc kiểu dữ liệu chặt hơn.
- Thêm kiểm thử phù hợp nếu rủi ro quan trọng.
- Chỉ suppression có lý do tại phạm vi nhỏ nếu công cụ vẫn không hiểu.

### 8.2. Ví dụ false negative do thiếu phạm vi

Nếu rule về secrets chỉ quét **src/main/resources**, một giá trị nhạy cảm được viết trong file cấu hình triển khai nằm ở vị trí khác có thể không được xét. Scanner có thể báo 0 phát hiện nhưng nguyên nhân là **không đọc tệp đó**, không phải giá trị an toàn.

Đây là lý do phải kiểm soát danh sách include/exclude, source set, module và các bước sinh artifact.

## 9. Chuỗi kiểm tra trong CI: mỗi lớp có một trách nhiệm

Một pipeline có thể sử dụng nhiều loại kiểm tra:

~~~text
Checkout source + build/config
             |
             v
       Source checks
   (style, AST, data-flow)
             |
             v
        Compile
     (javac, processors)
             |
             v
      Bytecode checks
     (.class và classpath)
             |
             v
      Unit/component tests
             |
             v
   Package / inspect artifacts
             |
             v
       Integration tests
             |
             v
       Deploy theo chính sách

  Configuration/SCA scans có thể được chạy song song
  ở những điểm có đủ đầu vào tương ứng.
~~~

Một số kiểm tra source cần compiler hoặc type resolution nên có thể chạy cùng giai đoạn compile. SCA trên artifact được đóng gói có thể cần đợi packaging; quét file khai báo có thể chạy sớm. Không nên coi sơ đồ này là thứ tự bắt buộc.

### 9.1. Ví dụ bảng phạm vi trong một dự án đa module

| Bước | Đầu vào đã chọn | Bằng chứng tạo ra | Cần tránh hiểu nhầm |
| --- | --- | --- | --- |
| Style/AST | Mọi tệp main Java thuộc các module mục tiêu | Vi phạm quy ước và rule source | Không chứng minh test source và generated source đã được quét |
| Compile | Source set và dependency của build | Cú pháp, kiểu và class files biên dịch được | Không chứng minh hành vi runtime đúng |
| Bytecode | Các class main mới build | Mẫu lỗi trong bytecode được phân tích | Không bao trùm tất cả thư viện hoặc code động |
| Configuration | Các file config, Dockerfile/IaC được khai báo | Cảnh báo policy trên các giá trị nguồn | Không biết hết override production |
| SCA | Cây phụ thuộc và artifact đã chọn | Package/version, cảnh báo tư vấn | Không xác nhận đường khai thác thực sự |
| Unit test | Code + dữ liệu test đã định nghĩa | Kết quả của các oracle cụ thể | Không kiểm chứng mọi tổ hợp |
| Integration test | Hạ tầng và cấu hình test | Hành vi tích hợp quan sát được | Môi trường test vẫn có thể khác production |

### 9.2. Vì sao một module bị bỏ sót là vấn đề

Giả sử repository có các module:

~~~text
checkout-api
checkout-domain
checkout-batch
~~~

Nếu cấu hình scanner chỉ chạy trên **checkout-api** và **checkout-domain**, một lỗi trong **checkout-batch** không thể được phát hiện bởi lần chạy đó. Kết luận chính xác phải là:

> Những check được cấu hình đã hoàn thành trên hai module được chọn; module batch chưa có bằng chứng tương đương.

Không nên viết “toàn bộ hệ thống sạch cảnh báo” khi pipeline chưa chứng minh đã quét toàn bộ phần mềm trong phạm vi phát hành.

## 10. Đọc báo cáo theo nguyên nhân, không theo nhãn màu

Một báo cáo tự động có thể nêu:

~~~text
RULE: POSSIBLE_NULL_DEREFERENCE
TARGET: checkout-domain / compiled classes
LOCATION: CustomerCode.length(...)
SEVERITY: warning
CONFIDENCE: medium
~~~

Đây là **mẫu mô tả giả định** để minh họa thông tin cần đọc, không phải đầu ra từ một công cụ đã chạy. Điều cần rút ra:

- **Rule:** phát hiện loại biểu hiện gì?
- **Target:** công cụ nhìn thấy tệp, module, class hay artifact nào?
- **Vị trí:** có thể lần về mã nguồn/điểm cấu hình nào?
- **Severity:** mức ưu tiên do công cụ/chính sách gán, không đồng nghĩa mức độ ảnh hưởng tuyệt đối.
- **Confidence:** độ tin cậy mà công cụ đánh giá cho suy luận, nếu công cụ có thuộc tính này.
- **Bằng chứng đường đi:** công cụ có chỉ ra luồng dữ liệu hoặc nhánh liên quan không?

Một cảnh báo “high severity” từ cấu hình nhưng không áp dụng ở môi trường đang chạy vẫn cần đánh giá phạm vi. Một cảnh báo mức thấp nhưng lặp lại ở đường xử lý quan trọng có thể cần ưu tiên. **Không nên chỉ đếm số cảnh báo mà bỏ qua bản chất và mức độ ảnh hưởng.**

### 10.1. Quy trình xử lý cảnh báo

1. **Xác nhận phạm vi:** công cụ đọc tệp, class và cấu hình phiên bản nào?
2. **Hiểu rule:** điều kiện phát hiện và giả định của công cụ là gì?
3. **Tái hiện lý do:** kiểm tra source, bytecode liên quan hoặc giá trị cấu hình.
4. **Đối chiếu hợp đồng:** có đường đi thực tế nào dẫn tới lỗi không?
5. **Quyết định sửa hoặc giảm rủi ro:** ưu tiên sửa mã/hợp đồng trước khi suppression.
6. **Nếu suppression cần thiết:** ghi lý do, phạm vi tối thiểu, người review và điều kiện xem lại.
7. **Giữ bằng chứng hồi quy:** thêm test, rule hoặc cấu hình phù hợp để lỗi không tái diễn.

Một cảnh báo “đã xử lý” có thể mang nhiều trạng thái: đã sửa, được chấp nhận có thời hạn, false positive có giải thích, hoặc còn chờ phân tích. Không nên gộp tất cả vào “không còn lỗi”.

## 11. Baseline và quality gate phải phản ánh phạm vi

Khi đưa phân tích tĩnh vào codebase có nhiều cảnh báo tồn đọng, nhóm có thể dùng **baseline** để ưu tiên không đưa thêm vấn đề mới. Nhưng baseline cũng dễ làm kết quả đẹp trên bảng điều khiển trong khi nợ kỹ thuật cũ vẫn còn nguyên.

Một cách đặt quality gate có căn cứ:

- **Mã mới:** chặn các lỗi nghiêm trọng có độ tin cậy cao theo chính sách.
- **Mã cũ:** duy trì danh sách cảnh báo đã xác nhận và có kế hoạch giảm dần.
- **Cấu hình mới:** kiểm tra các quy tắc rủi ro trước khi được merge.
- **Phụ thuộc:** có quy trình đánh giá lỗ hổng và cập nhật, kể cả dependency bắc cầu.
- **Quyền miễn trừ:** có lý do, người phê duyệt, thời hạn hoặc điều kiện xem lại.

Chú ý rằng công cụ báo **“0 new issues”** có thể chỉ là so sánh với baseline, **không đồng nghĩa “0 issues trong toàn bộ phần mềm”**.

### 11.1. Cấu hình và phiên bản của chính công cụ cũng là đầu vào

Kết quả phụ thuộc:

- Phiên bản scanner và tập quy tắc được bật.
- JDK và bytecode version mà scanner hỗ trợ.
- Các path include/exclude và scope module.
- Classpath, dependency resolution và dữ liệu cấu hình.
- Profile build, annotation processor, generated source.
- Baseline, suppression và ngưỡng quality gate.

Nếu nâng cấp công cụ, số cảnh báo có thể tăng vì rule mới chứ không phải mã đột nhiên xấu hơn. Nếu giảm cảnh báo vì có rule bị tắt, đó không chứng minh chất lượng đã cải thiện. Cần xem xét **độ bao phủ và phiên bản quy tắc** cùng với số lượng cảnh báo.

## 12. Khi nào kiểm tra mã nguồn, bytecode hay cấu hình trước?

Có thể chọn lớp kiểm tra theo câu hỏi cần trả lời:

| Mục tiêu | Kiểm tra ưu tiên | Cần bổ sung |
| --- | --- | --- |
| Thống nhất tên, định dạng, cấu trúc Java | Source/style/AST | Review khả năng đọc và ngoại lệ hợp lý |
| Phát hiện mẫu null hoặc sử dụng API sai | Source có thông tin kiểu và/hoặc bytecode analyzer | Unit test cho các đường đi quan trọng |
| Rà soát class sinh ra và mã đã biên dịch | Bytecode sau build | Phân tích phần generated source khi cần |
| Kiểm soát endpoint, quyền, timeout khai báo | Configuration scan | Kiểm tra effective configuration tại runtime |
| Rà soát dependency dễ tổn thương | SCA/manifest/SBOM hoặc artifact scan | Đánh giá ảnh hưởng và quy trình cập nhật |
| Đúng ngưỡng nghiệp vụ, lỗi và trạng thái | Unit/component/integration test có oracle | Review hợp đồng và các ca biên |
| Ngăn hai yêu cầu cùng ghi đè dữ liệu | Concurrency/integration test, DB constraints | Thiết kế giao dịch và giám sát |
| Xác nhận tính năng thực sự chạy trong production | Smoke/monitoring/quan sát runtime | Kết hợp kiểm tra tĩnh và quy trình phát hành |

**Không cần chọn chỉ một loại.** Source analysis và bytecode analysis có thể phát hiện những rủi ro khác nhau trên cùng một mã; quét cấu hình giúp thấy một nhóm rủi ro mà hai loại kia thường không xử lý đủ.

## 13. Những hiểu nhầm thường gặp

**“Static analysis đã xanh nên mã chắc chắn đúng.”** Công cụ chỉ kiểm tra những rule và đầu vào được cấu hình. Lỗi nghiệp vụ ở ngưỡng hoặc sai tác dụng phụ vẫn cần kiểm thử.

**“Phân tích source cũng nhìn thấy đúng mọi class sau build.”** Mã sinh ra, annotation processing, compiler-generated methods và biến thể build có thể làm class cuối khác vùng source được quét.

**“Bytecode có hết thông tin từ source.”** Bytecode không giữ nguyên bình luận, định dạng và mọi chi tiết cấp cao để đánh giá khả năng đọc.

**“Quét bytecode thay thế kiểm tra kiểu khi compile.”** Compilation xác nhận một tập tính chất ngôn ngữ; bytecode analyzer dùng rule khác để tìm mẫu rủi ro. Hai lớp không thể thay thế cho nhau.

**“Quét YAML đã xanh nên cấu hình production an toàn.”** Biến môi trường, profile, override và hạ tầng có thể khiến cấu hình hiệu lực khác repository.

**“Có CVE trong dependency nghĩa là ứng dụng chắc chắn khai thác được.”** Cần đánh giá thành phần, cách sử dụng, phạm vi triển khai và dữ liệu tư vấn. Nhưng cũng không được bỏ qua chỉ vì chưa thấy lời gọi trực tiếp.

**“Ít cảnh báo hơn luôn là tốt hơn.”** Số cảnh báo có thể giảm vì exclude, tắt rule, thay baseline hoặc không build được module. Cần kiểm tra phạm vi trước khi kết luận.

**“Mọi cảnh báo đều là bug chắc chắn.”** Phân tích tĩnh có false positive. Điều tra, giải thích và bổ sung bằng chứng thích hợp trước khi quyết định.

**“Công cụ không báo gì nghĩa là không có lỗ hổng.”** Công cụ không tìm những gì không được mô hình hóa, không được cấu hình hoặc nằm ngoài phạm vi dữ liệu của nó.

## 14. Tình huống thực hành

Một nhóm phát triển dịch vụ đặt hàng Java có ba module:

~~~text
orders-api
orders-domain
orders-worker
~~~

Ứng dụng dùng **Spring Boot**, xây dựng bằng công cụ build Java, có JAR của thư viện bên ngoài và các file cấu hình theo môi trường. Pipeline hiện tại:

1. Chạy formatter và rule đặt tên trên **orders-api** cùng **orders-domain**.
2. Biên dịch toàn bộ ba module.
3. Chạy bytecode analyzer chỉ với lớp của **orders-api**.
4. Quét **application.yml** mặc định nhưng không nhận các file override của môi trường.
5. Kiểm tra dependency khai báo trong file build của module API.
6. Chạy một số unit test cho phép tính tổng tiền.

Trang CI báo **“Quality Gate: PASS”**.

### Câu hỏi

1. Kết quả PASS đang cung cấp bằng chứng cụ thể cho những **module** và **loại kiểm tra** nào?
2. Module **orders-worker** có được phân tích bytecode không? Vì sao điều này quan trọng nếu nó chạy tác vụ gửi email hoặc cập nhật trạng thái?
3. Nếu có lớp được annotation processor tạo ra, những bước hiện tại đã kiểm tra nó ở đâu? Có chắc mọi lớp sinh ra được đưa vào bytecode scanner không?
4. Vì sao quét **application.yml** mặc định chưa đủ để kết luận cấu hình production hợp lệ?
5. Một thư viện được đưa vào JAR của worker qua dependency bắc cầu có chắc đã được kiểm tra đầy đủ không?
6. Nếu quy tắc miễn phí vận chuyển sai ở ngưỡng **500.000 VND**, kiểm tra nào có cơ hội phát hiện chắc chắn nhất khi có oracle?
7. Hãy đề xuất thay đổi phạm vi scan và cách viết lại thông điệp PASS cho chính xác.

### Gợi ý đối chiếu

- Rule style chỉ có bằng chứng trên hai module được khai báo; worker chưa có bằng chứng style tương ứng.
- Analyzer bytecode chỉ nhận class của API, nên không thể suy ra chất lượng bytecode của domain và worker. Nếu có generated class trong API, cần xác nhận class đó thực sự nằm trong đường quét.
- Cấu hình runtime có thể được ghi đè bởi profile, biến môi trường hoặc cấu hình triển khai; cần kiểm tra phạm vi effective configuration khi đánh giá rủi ro vận hành.
- SCA chỉ dựa trên dependency khai báo của API có thể bỏ qua dependency của worker và artifact được đóng gói ở bước khác.
- Lỗi nghiệp vụ tại ngưỡng cần unit test có oracle độc lập, ví dụ xác nhận đúng giá trị **500.000 VND** được miễn phí nếu hợp đồng nói “từ 500.000 trở lên”.
- Có thể mở rộng scan tới các module cần phát hành, ghi rõ phạm vi main/test/generated, quét phụ thuộc và cấu hình thực sự triển khai, rồi kết hợp unit/integration tests. Thông điệp PASS nên nói rõ **những policy được áp dụng trên những artifact được chọn**, không gọi đó là chứng nhận hệ thống không có lỗi.

## 15. Ghi nhớ

- **Phân tích nguồn** quan sát mã và cấu trúc cú pháp/kiểu; **phân tích bytecode** quan sát mã JVM sau biên dịch; **quét cấu hình** quan sát khai báo build, vận hành và triển khai. Mỗi lớp cung cấp bằng chứng khác nhau.
- Công cụ chỉ kiểm tra **đầu vào, module, rule, classpath và phiên bản** đã được cấu hình. Phần không được quét không thể được suy ra là an toàn.
- Generated source, bytecode do compiler tạo, profile runtime và dependency bắc cầu làm **phạm vi thực tế** phức tạp hơn tên một công cụ.
- **False positive, false negative, baseline và suppression** phải được quản lý minh bạch để báo cáo có ý nghĩa.
- Kết hợp kiểm tra source, bytecode, cấu hình và **kiểm thử có oracle** giúp giảm rủi ro; không nên biến một trạng thái CI màu xanh thành lời khẳng định phần mềm đã đúng hoàn toàn.
