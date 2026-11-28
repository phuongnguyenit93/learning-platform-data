# Kiểm thử payload độc hại — Chứng minh dữ liệu không trở thành chỉ thị

## 1. Kiểm thử phải chứng minh điều gì?

Một đội kiểm thử gửi một danh sách chuỗi “tấn công” vào API. Tất cả request trả về mã 200 hoặc 400, không có lỗi rõ ràng. Đội kết luận chức năng không có injection.

Kết luận đó chưa có cơ sở đủ mạnh. Mã HTTP không cho biết query có bị đổi nghĩa, tiến trình có được gọi thêm, dữ liệu có bị lưu rồi thực thi ở luồng khác hay trình duyệt có tạo cấu trúc ngoài dự kiến hay không.

Trong chương Injection defense, **kiểm thử payload độc hại** là việc đưa dữ liệu được thiết kế để thách thức một ranh giới diễn giải, rồi quan sát xem dữ liệu có giữ đúng vai trò theo hợp đồng hay không.

Mục tiêu của bài là chuyển hoạt động “thử một số payload” thành yêu cầu bảo mật có thể kiểm chứng:

- Biết payload đi từ nguồn nào tới nơi diễn giải nào.
- Chọn ca thử theo ngôn ngữ, vị trí và kiểm soát cần xác minh.
- Xác định kết quả đúng trước khi chạy.
- Quan sát cả response, cấu trúc thực thi và tác động liên quan.
- Phân biệt bằng chứng đạt yêu cầu, phát hiện lỗi và trường hợp chưa đủ bằng chứng.
- Giữ dữ liệu thử và môi trường thử trong phạm vi được quản lý.

OWASP phân loại injection theo interpreter hoặc sink như SQL, OS command, LDAP, XPath và nội dung trình duyệt. Cách chọn payload phải theo ranh giới tương ứng, thay vì dùng một bộ chuỗi chung cho mọi chức năng. Tham khảo [OWASP Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Injection_Prevention_Cheat_Sheet.html).

## 2. Payload, đường đi và oracle là ba thành phần khác nhau

### 2.1. Payload là dữ liệu thử, không phải kết luận

Payload có thể là một dấu nháy, chuỗi trông giống toán tử truy vấn, tên bắt đầu bằng dấu gạch ngang hoặc đoạn markup có marker. Nó chỉ có ý nghĩa khi đặt vào đúng ngữ cảnh.

Một chuỗi giống SQL trong ô ghi chú có thể hoàn toàn hợp lệ nếu được lưu bằng binding và hiển thị như text. Không nên đặt kỳ vọng rằng mọi dữ liệu có vẻ “độc hại” đều phải bị từ chối.

Ngược lại, một chuỗi chỉ gồm chữ và số có thể chọn một tài nguyên ngoài quyền. Tập ký tự trông bình thường không chứng minh ý nghĩa nghiệp vụ an toàn.

### 2.2. Đường đi cho biết dữ liệu được diễn giải ở đâu

Cần xác định:

```text
Nguồn đầu vào
    -> parser / giải mã
    -> validation / chuẩn hóa
    -> lưu trữ hoặc hàng đợi
    -> nơi sử dụng
    -> interpreter hoặc sink
    -> tác động quan sát
```

Nguồn có thể là query parameter, JSON, multipart metadata, header, file import hoặc một bản ghi đã lưu. Sink có thể nằm ở job nền, trang quản trị hoặc công cụ xuất báo cáo chứ không phải endpoint nhận dữ liệu ban đầu.

### 2.3. Oracle là quy tắc quyết định kết quả đúng

Trong kiểm thử, **oracle** là tiêu chí giúp xác định hành vi có đúng yêu cầu hay không. Ví dụ:

- Query template giữ nguyên và payload được bind thành một giá trị.
- Launcher nhận đúng một executable cùng tập đối số được phép.
- Một field text được trình duyệt biểu diễn thành text node, không thành element do payload tạo.
- Không có hàng của tenant khác xuất hiện trong kết quả.
- Không có tệp ngoài vùng thử bị tạo hoặc thay đổi.
- Input sai kiểu bị từ chối trước khi tới sink.

“Không thấy thông báo lỗi” là một quan sát, không phải oracle đủ cho mọi ranh giới.

## 3. Lập danh mục điểm kiểm thử từ mô hình đe dọa

Trước khi chọn payload, lập một bảng tối thiểu:

| Thành phần | Nội dung cần ghi |
|---|---|
| Chức năng | Tìm kiếm, cập nhật, upload, xuất báo cáo hoặc job cụ thể |
| Quyền | Vai trò và tenant được phép thực hiện |
| Nguồn | Field, header, file, message hoặc dữ liệu lưu trước đó |
| Biến đổi | Parse, giải mã, trim, chuẩn hóa, ghép hoặc serialize |
| Sink | API query, shell, argv, template engine, DOM hoặc parser khác |
| Kiểm soát kỳ vọng | Binding, mapping cố định, safe API, encoding hoặc sanitizer |
| Oracle | Cấu trúc và tác động được phép |
| Điểm quan sát | Response, query adapter, launcher, DOM, database, queue |
| Dữ liệu thử | Fixture và marker riêng cho lần chạy |
| Giới hạn | Nhánh chưa quan sát được, nền tảng hoặc cấu hình chưa thử |

Ví dụ một endpoint tìm kiếm có thể có hai sink riêng: truy vấn database để tìm dữ liệu và trang HTML hiển thị cụm từ tìm kiếm. Payload và oracle cho hai sink này không giống nhau.

Một chức năng lưu ghi chú có thể cần kiểm thử ba lần sử dụng: trang người dùng, trang quản trị và email thông báo. Chỉ kiểm tra response của lần lưu chưa bao phủ các đường diễn giải sau đó.

Danh mục không cần liệt kê mọi biến nội bộ, nhưng phải chỉ ra những nơi dữ liệu vượt qua ranh giới tin cậy hoặc được trao ý nghĩa điều khiển mới.

## 4. Chọn payload theo một giả thuyết cụ thể

Một ca thử tốt có thể được diễn đạt:

> Nếu giá trị của field X bị ghép vào cấu trúc Y, biến thể P sẽ làm thay đổi quan sát Z. Yêu cầu đúng là Z vẫn giữ theo hợp đồng.

Đây là cách xây ca thử theo giả thuyết, thay vì gửi nhiều chuỗi rồi tìm một response khác lạ.

| Nhóm | Probe minh họa | Giả thuyết cần kiểm tra | Oracle phù hợp |
|---|---|---|---|
| SQL hoặc query language | Dấu nháy và chuỗi giống điều kiện | Input có làm đổi cấu trúc query không? | Template, bind và tập hàng trả về |
| NoSQL dạng object | Một object chứa operator ở field phải là string | Input có được chuyển thành cấu trúc truy vấn không? | Kiểu bị từ chối; cấu trúc query không bị mở rộng |
| OS command | Chuỗi chứa separator hoặc xuống dòng | Input có bị đưa vào mã shell không? | Launcher và argv; không có tác vụ ngoài contract |
| Argument hoặc option | Giá trị như `--help` | Dữ liệu có bị hiểu thành option ngoài tập không? | Giá trị được từ chối hoặc xử lý đúng vị trí đã chốt |
| Template | Biểu thức số học vô hại như `{{7*7}}` | Nội dung thường có bị đánh giá thành template không? | Giá trị giữ nguyên hoặc hành vi đúng chức năng |
| HTML text | Markup có marker, không cần script | Field text có trở thành cấu trúc HTML không? | DOM thể hiện text theo yêu cầu |
| Header hoặc log | Marker kèm biểu diễn CR/LF | Dữ liệu có tạo field hoặc bản ghi mới không? | Cấu trúc header/log không bị thay đổi |
| Đường dẫn | Thành phần cha hoặc separator trong vùng thử | Dữ liệu có chọn được tài nguyên ngoài vùng không? | Target thực tế và trạng thái vùng thử |

Các probe trong bảng không phải payload phổ quát. Ví dụ một template editor được phép đánh giá biểu thức; kết quả 49 trong chức năng đó không tự là lỗi. Một field plain text bất ngờ đánh giá cùng chuỗi mới là hành vi cần điều tra.

Tương tự, một hệ thống rich text có thể cho phép thẻ HTML nhất định. Việc thấy thẻ xuất hiện không đủ để kết luận XSS. Cần kiểm tra chính sách nội dung và khả năng tạo hành vi ngoài quyền.

## 5. Xây bộ dữ liệu thử có khả năng phân biệt kết quả

### 5.1. Dùng fixture nhiều phạm vi quyền

Với một chức năng tìm kiếm theo tenant, có thể chuẩn bị:

```text
Tenant A:
  A1: name = Normal customer
  A2: name = QA_7F31' OR 'x'='x

Tenant B:
  B1: name = OTHER_TENANT_MARKER
```

Nếu chức năng là tìm chính xác theo tên, request của tenant A tìm chuỗi tên A2 phải chỉ trả A2. Không trả A1 hoặc B1.

Cách bố trí này kiểm tra được nhiều điều:

- Hệ thống không từ chối dữ liệu chỉ vì có dấu nháy nếu hợp đồng cho phép.
- Payload được đối chiếu như một giá trị literal.
- Kết quả không mở rộng thành các hàng không khớp.
- Điều kiện tenant vẫn giữ hiệu lực.

Nếu fixture chỉ có một hàng, một query bị mở rộng có thể vẫn trả một hàng và làm test trông như đạt.

### 5.2. Marker riêng cho mỗi lần chạy

Marker giúp liên kết input, trạng thái và kết quả qua nhiều thành phần. Nên dùng một mã thử không phải credential thật, đủ khác biệt với dữ liệu nền và có giới hạn độ dài.

Marker có thể kết hợp case ID và run ID. Không dùng thông tin cá nhân hoặc secret để tăng tính “thực tế” của payload.

Phải biết marker được kỳ vọng xuất hiện ở đâu. Marker hiện trong log không tự chứng minh command injection; nó có thể chỉ được ghi như dữ liệu. Marker hiện trong một cấu trúc DOM được tạo ngoài hợp đồng lại là loại quan sát khác.

### 5.3. Phân biệt đối chứng với payload nghi ngờ

Mỗi nhóm nên có:

- Input nghiệp vụ thông thường để xác nhận luồng hoạt động.
- Input hợp lệ nhưng có ký tự dễ bị xử lý sai, như tên có dấu nháy.
- Probe thử thay đổi cấu trúc.
- Trường hợp sai hợp đồng cần bị từ chối.
- Tình huống kiểm tra cơ chế quan sát có hoạt động.

Nếu cả request bình thường cũng bị lỗi, chưa thể quy khác biệt cho payload.

## 6. Xác định kết quả mong đợi trước khi chạy

Ba hành vi thường có thể đúng, nhưng phải chọn theo từng field và chức năng:

1. **Từ chối:** dữ liệu không đúng kiểu hoặc không thuộc tập giá trị được phép.
2. **Chấp nhận như dữ liệu:** nội dung tự do được bind, lưu hoặc hiển thị đúng ngữ cảnh.
3. **Biến đổi theo chính sách:** ví dụ rich text được sanitizer xử lý theo hợp đồng đã công bố.

Không nên viết một ca có tiêu chí “trả 400 hoặc giữ literal hoặc sanitize đều được”. Tiêu chí quá rộng có thể chấp nhận một lỗi nghiệp vụ hoặc một kiểm soát không nằm trong thiết kế.

Một ca thử minh họa:

```yaml
caseId: INJ-SQL-LITERAL-01
requirement: QUERY_VALUES_ARE_BOUND
entryPoint: customer-search.name
context: exact-match-search
fixture: tenant-a-and-tenant-b
input: "QA_7F31' OR 'x'='x"
expected:
  acceptedAsData: true
  queryTemplateUnchanged: true
  boundValueEqualsInput: true
  returnedIds:
    - A2
  forbiddenReturnedIds:
    - A1
    - B1
  unexpectedWrites: 0
evidence:
  - query-adapter-observation
  - response-result-set
  - fixture-state-after-request
```

Đây là mô tả trong bài, không phải schema bắt buộc của một công cụ kiểm thử. Điểm quan trọng là case có nguồn, ngữ cảnh, oracle và bằng chứng gắn với cùng một yêu cầu.

## 7. Kiểm thử tại sink trước khi kết luận từ response

### 7.1. Query sink

Với truy vấn tham số hóa, cần quan sát mẫu query và việc bind, sau đó xác minh ngữ nghĩa trên database thử.

Không chỉ kiểm tra method `prepareStatement` đã được gọi: ứng dụng có thể đã nối input vào SQL trước khi gọi method đó. Cũng không xem một chuỗi query được render trong log là bằng chứng duy nhất, vì công cụ quan sát có thể hiển thị giá trị dù driver đã bind.

Các phần cấu trúc như sort phải có oracle riêng: chỉ xuất hiện một fragment trong mapping cố định. Gửi sort ngoài tập phải bị từ chối theo hợp đồng, không được âm thầm chuyển thành raw SQL.

Tham khảo ranh giới dữ liệu và cấu trúc trong [OWASP SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html).

### 7.2. Command và argument sink

Dùng launcher thử nghiệm để ghi nhận executable, từng đối số và môi trường được phép. Với probe chứa separator, xác minh không có chuỗi shell tổng hợp ngoài thiết kế.

Tách argv đúng chưa chứng minh mọi đối số an toàn về ý nghĩa. Cần thử option-like input, đường dẫn ngoài quyền hoặc lựa chọn công cụ không được phép theo hợp đồng.

Một chương trình probe vô hại có thể ghi lại cấu trúc đối số trong vùng thử. Không cần chạy thao tác phá dữ liệu để chứng minh lỗi ranh giới.

### 7.3. Browser sink

Với field plain text, có thể dùng marker trong markup như:

```html
<b data-qa="QA_7F31">probe</b>
```

Oracle không chỉ là “response chứa chuỗi đó”. Cần xác minh trình duyệt hiển thị nội dung như text hay tạo một element `b` do input cung cấp.

Một probe markup không chứng minh khả năng chạy script. Nếu yêu cầu cần kiểm tra ranh giới JavaScript, attribute hoặc URL, phải thiết kế ca phù hợp với ngữ cảnh và dùng tín hiệu thử có kiểm soát.

Phải kiểm tra DOM sau các thao tác client-side liên quan, không chỉ HTML response ban đầu. Nội dung ban đầu an toàn có thể đi qua một API DOM khác ở bước sau.

OWASP WSTG nhấn mạnh việc phân tích ngữ cảnh phản chiếu khi kiểm thử XSS. Xem [Testing for Reflected Cross Site Scripting](https://owasp.github.io/www-project-web-security-testing-guide/stable/4-Web_Application_Security_Testing/07-Input_Validation_Testing/01-Testing_for_Reflected_Cross_Site_Scripting).

### 7.4. Sink bất đồng bộ hoặc lưu trữ

Payload có thể được chấp nhận và lưu đúng cách nhưng bị ghép thành query hoặc template khi một job khác chạy. Ca thử phải đi tới bước tiêu thụ dữ liệu.

Bằng chứng cần liên kết được bản ghi gốc, event hoặc job ID, phiên bản consumer và kết quả sau xử lý. Không kết luận PASS ngay khi endpoint lưu trả thành công.

## 8. Ví dụ Java: kiểm tra cấu trúc query qua adapter ghi nhận

Ví dụ sau chỉ minh họa phép thử ở ranh giới ứng dụng và query adapter. Nó không kết nối database và không chứng minh tính đúng của driver hay kết quả SQL.

```java
import java.util.List;
import java.util.Objects;

public final class InjectionBoundaryTestExample {
    private static final String EXPECTED_SQL =
            "SELECT id FROM customers "
            + "WHERE tenant_id = ? AND customer_name = ?";

    record QueryCall(String sql, List<String> values) {
        QueryCall {
            Objects.requireNonNull(sql);
            values = List.copyOf(values);
        }
    }

    interface QueryGateway {
        void execute(QueryCall call);
    }

    static final class CustomerRepository {
        private final QueryGateway gateway;

        CustomerRepository(QueryGateway gateway) {
            this.gateway = Objects.requireNonNull(gateway);
        }

        void findExact(String authorizedTenantId, String name) {
            Objects.requireNonNull(authorizedTenantId);
            Objects.requireNonNull(name);

            gateway.execute(new QueryCall(
                    EXPECTED_SQL,
                    List.of(authorizedTenantId, name)));
        }
    }

    static final class RecordingGateway implements QueryGateway {
        private int callCount;
        private QueryCall lastCall;

        @Override
        public void execute(QueryCall call) {
            callCount++;
            lastCall = call;
        }
    }

    static void verifyBoundary(String payload) {
        RecordingGateway gateway = new RecordingGateway();
        CustomerRepository repository = new CustomerRepository(gateway);

        // Giá trị tenant là fixture của ngữ cảnh đã phân quyền.
        String tenant = "tenant-a";
        repository.findExact(tenant, payload);

        require(gateway.callCount == 1, "UNEXPECTED_CALL_COUNT");
        require(gateway.lastCall != null, "MISSING_QUERY_CALL");
        require(EXPECTED_SQL.equals(gateway.lastCall.sql()),
                "QUERY_TEMPLATE_CHANGED");
        require(List.of(tenant, payload).equals(
                        gateway.lastCall.values()),
                "BOUND_VALUES_CHANGED");
    }

    static void require(boolean condition, String code) {
        if (!condition) {
            throw new AssertionError(code);
        }
    }

    public static void main(String[] args) {
        List<String> cases = List.of(
                "Normal customer",
                "O'Neil",
                "QA_7F31' OR 'x'='x",
                "QA_7F31/*probe*/",
                "Khách hàng thử nghiệm");

        for (String value : cases) {
            verifyBoundary(value);
        }
    }
}
```

Phép thử này kiểm tra hai điều tách biệt: mẫu SQL không thay đổi và dữ liệu đi qua danh sách giá trị. Không dùng `assert` phụ thuộc vào việc bật tùy chọn JVM; helper ném lỗi rõ ràng nếu điều kiện không đạt.

Tuy nhiên, adapter thật vẫn có thể bị viết sai bằng cách lấy `values` rồi nội suy vào SQL. Vì vậy cần kiểm thử adapter JDBC thật và database fixture. Một test double không được dùng để che khoảng trống ở tầng sau.

Tương tự, tên tham số `authorizedTenantId` không thực hiện phân quyền. Cần ca riêng xác minh tenant được lấy từ ngữ cảnh tin cậy và caller không thể chọn dữ liệu ngoài quyền.

Nếu muốn kiểm chứng test harness phát hiện sai ranh giới, có thể dùng một fixture cố ý sai chỉ trong bộ thử cô lập, không thực thi query nguy hiểm. Harness phải báo lỗi khi query template bị thay hoặc khi values không được giữ riêng.

## 9. Kiểm thử biến đổi và cách biểu diễn

Một payload có thể đi qua URL decoding, JSON parsing, Unicode normalization hoặc logic xử lý lặp tham số. Các phép biến đổi phải được mô tả theo giao thức.

Nhóm ca thử nên bao phủ:

- Biểu diễn trực tiếp của ký tự đặc biệt trong field cho phép.
- Biểu diễn encoding hợp lệ của giao thức tương ứng.
- Input sai encoding hoặc sai kiểu.
- Ký tự Unicode và các dạng chuẩn hóa nếu sản phẩm có xử lý.
- Field lặp hoặc nguồn dữ liệu mâu thuẫn nếu parser hỗ trợ.
- Vị trí khác nhau như query, body, header hoặc tên tệp.
- Biên độ dài và cấu trúc lồng nhau theo ngân sách đã định nghĩa.

Không tự giải mã lặp payload cho tới khi “trông nguy hiểm”. Cách đó có thể tạo một đường xử lý không tồn tại trong hệ thống thật. Mỗi tầng phải được kiểm tra theo trách nhiệm parse cụ thể.

Khi có hai lớp nhìn thấy hai biểu diễn khác nhau, cần quan sát cả trước và sau biến đổi. Một bộ lọc ở gateway chặn chuỗi trực tiếp không chứng minh repository hoặc template engine an toàn với mọi dữ liệu hợp lệ tới được chúng.

Fuzzing có ích để tạo biến thể, nhưng phải có thuộc tính kiểm tra rõ ràng. Gửi nhiều chuỗi mà không có oracle chỉ làm tăng lưu lượng và số response cần đọc.

## 10. Kiểm thử dữ liệu lưu rồi sử dụng lại

Một kịch bản kiểm thử nhiều bước có thể gồm:

```text
Tạo dữ liệu chứa marker
        |
        v
Xác nhận lưu đúng và lấy record ID
        |
        v
Kích hoạt luồng đọc / job / trang quản trị
        |
        v
Chờ điều kiện hoàn tất được định nghĩa
        |
        v
Quan sát sink và tác động
        |
        v
Dọn fixture qua ID thuộc run
```

Cần xác minh payload thực sự đã tới bước tiêu thụ. Nếu job không chạy hoặc đọc nhầm bản ghi, việc không có tác động không phải là bằng chứng phòng vệ.

Đối với stored XSS, trang quản trị có thể dùng template khác trang người dùng. Đối với second-order query injection, báo cáo hoặc tác vụ đồng bộ có thể dùng repository khác với endpoint lưu ban đầu.

Các ca thử phải phân biệt:

- Lưu payload thất bại theo hợp đồng.
- Lưu thành công và xử lý downstream như dữ liệu.
- Lưu thành công nhưng consumer chưa được quan sát.
- Downstream diễn giải dữ liệu thành chỉ thị ngoài dự kiến.

Trạng thái thứ ba là chưa đủ bằng chứng, không phải PASS.

## 11. Tổ chức môi trường và dữ liệu thử

Kiểm thử payload nên có một phạm vi hệ thống và dữ liệu được xác định. Đây là điều kiện để kết quả lặp lại được và không gây tác động ngoài mục tiêu kiểm thử.

Một cấu hình thử nghiệm phù hợp có thể có:

- Database fixture và tenant thử riêng.
- Tài khoản với vai trò cần kiểm tra, không dùng quyền quản trị làm mặc định.
- Kho tệp, queue và worker thuộc run hoặc namespace thử.
- Các đích tích hợp giả hoặc endpoint nội bộ do đội thử quản lý.
- Giới hạn request rate, số ca, thời gian và tài nguyên.
- Cơ chế liên kết bằng run ID và case ID.
- Cách dọn dữ liệu dựa trên ID hoặc namespace đáng tin.

Không dùng địa chỉ bên ngoài hoặc tài nguyên thật làm tín hiệu thử nếu không nằm trong thiết kế phạm vi. Một marker cục bộ, adapter ghi nhận hoặc probe nội bộ thường đủ để kiểm tra ranh giới cần thiết.

Khi kiểm tra timing, phải có baseline, số lần lặp và cách tách tác động của tải hệ thống. Một response chậm đơn lẻ không chứng minh có diễn giải lệnh. Không chọn các tác vụ kéo dài không giới hạn chỉ để tạo khác biệt dễ thấy.

Cleanup cũng là một thao tác cần thiết kế: không dựng lệnh xóa từ chính payload đang thử. Dùng record ID, job ID hoặc thư mục thử đã được xác định trước, và xác nhận trạng thái sau dọn.

## 12. Bộ yêu cầu bảo mật cho hoạt động kiểm thử

Các mã sau là ví dụ, cần gắn với chức năng và bộ bằng chứng của dự án.

### PAYTEST-01 — Có mapping từ yêu cầu tới sink và ca thử

Mỗi ranh giới injection thuộc phạm vi phải có yêu cầu, nguồn dữ liệu, sink, kiểm soát kỳ vọng và ít nhất các ca đại diện phù hợp. Không chỉ ghi tên scanner hoặc số payload đã chạy.

**Bằng chứng:** bảng truy vết yêu cầu, sink và test case; danh sách nhánh chưa bao phủ.

### PAYTEST-02 — Mỗi ca có oracle trước khi chạy

Kết quả chấp nhận, từ chối hoặc biến đổi phải được xác định theo hợp đồng trước khi thực thi. Không diễn giải mọi response là thành công sau khi xem kết quả.

**Bằng chứng:** định nghĩa case có expected behavior, trạng thái dữ liệu và điểm quan sát.

### PAYTEST-03 — Bao phủ các đường sử dụng dữ liệu liên quan

Kiểm thử phải bao gồm đường trực tiếp, dữ liệu lưu rồi dùng lại, job bất đồng bộ và đầu ra có ngữ cảnh khác trong phạm vi chức năng.

**Bằng chứng:** record/job ID được liên kết; trạng thái consumer và quan sát sink thực sự đã chạy.

### PAYTEST-04 — Kiểm tra cả cấu trúc lẫn tác động

Không chỉ dựa vào status code hoặc chuỗi response. Phải có bằng chứng phù hợp về query, argv, DOM hoặc cấu trúc interpreter, cùng dữ liệu hay tác động quan trọng theo yêu cầu.

**Bằng chứng:** log adapter đã giảm nhạy cảm, snapshot trạng thái fixture, DOM assertion hoặc probe output có cấu trúc.

### PAYTEST-05 — Có đối chứng và kiểm tra harness

Bộ thử phải xác nhận luồng bình thường chạy được và điểm quan sát hoạt động. Khi thích hợp, dùng fixture hoặc mutation cô lập để chứng minh test phát hiện được sai ranh giới.

**Bằng chứng:** baseline và kết quả kiểm tra harness; không phụ thuộc vào việc không thu được dữ liệu.

### PAYTEST-06 — Phân biệt PASS, FAIL và chưa đủ bằng chứng

Không có tín hiệu không tự động là PASS. Timeout của harness, thiếu quyền quan sát, consumer không chạy hoặc artifact bị mất phải được ghi nhận đúng trạng thái.

**Bằng chứng:** quy tắc phân loại và report có lý do; danh sách ca chưa thực thi hoặc chưa kết luận.

### PAYTEST-07 — Dữ liệu và tác động thử được quản lý

Payload, fixture, tài khoản, đích tích hợp và ngân sách thử phải thuộc phạm vi đã xác định. Không dùng credential thật làm marker hoặc đưa dữ liệu nhạy cảm vào artifact.

**Bằng chứng:** cấu hình môi trường thử, danh mục fixture và kết quả cleanup.

### PAYTEST-08 — Corpus và cấu hình có khả năng tái hiện

Bộ payload phải có phiên bản hoặc nguồn tái tạo; các lựa chọn nền tảng, parser, driver và engine quan trọng phải được ghi lại. Với fuzzing, lưu seed và cách sinh khi phù hợp.

**Bằng chứng:** case ID, corpus version, environment version và dữ liệu tái hiện tối thiểu.

### PAYTEST-09 — Phát hiện được chuyển thành regression có oracle

Sau khi xác định một lỗi, phải có ca tái hiện và oracle cho hành vi đúng, không chỉ thêm nguyên payload vào một blacklist. Xác minh sửa lỗi trên cùng ranh giới và các nhánh liên quan.

**Bằng chứng:** liên kết phát hiện, yêu cầu, thay đổi kiểm soát và kết quả regression.

## 13. Phân loại kết quả để tránh kết luận sai

| Trạng thái | Ý nghĩa | Ví dụ |
|---|---|---|
| PASS | Ca đã chạy tới điểm cần thiết và đạt oracle | Query bind đúng, chỉ trả hàng fixture được phép |
| FAIL | Có bằng chứng vi phạm yêu cầu | Dữ liệu tenant khác xuất hiện hoặc template bị đánh giá ngoài chức năng |
| INCONCLUSIVE | Đã thử nhưng chưa đủ bằng chứng | Consumer chưa được quan sát, thiếu artifact hoặc tín hiệu không phân biệt được |
| NOT_RUN | Chưa thực thi ca | Môi trường tương ứng chưa có |
| BLOCKED | Không thể thực hiện do điều kiện cụ thể | Thiếu tài khoản vai trò cần thử hoặc dependency thử chưa sẵn sàng |

Tên trạng thái có thể khác theo công cụ, nhưng ý nghĩa phải rõ. Không gộp NOT_RUN hoặc INCONCLUSIVE vào tỷ lệ PASS.

Cũng cần phân biệt phát hiện và nguyên nhân:

- Lỗi 500 có thể là bug validation, không nhất thiết injection.
- Response khác nhau có thể do dữ liệu fixture hoặc phân quyền.
- Marker xuất hiện có thể chỉ là phản chiếu an toàn.
- Một tập kết quả rộng hơn có thể do wildcard được sản phẩm cho phép.
- Một request bị WAF chặn chưa chứng minh sink phía sau đã được bảo vệ.
- Trình duyệt không chạy hành vi có thể do CSP hoặc một lớp khác; vẫn cần đánh giá kiểm soát nền và phạm vi yêu cầu.

Không nên ép mọi quan sát thành “có lỗ hổng” hoặc “hoàn toàn an toàn”. Report tốt nêu bằng chứng, cách tái hiện và giới hạn kết luận.

## 14. Thiết kế báo cáo và tích hợp regression

Một bản ghi kết quả tối thiểu có thể gồm:

```text
runId
caseId
requirementId
entryPoint
sink
roleAndTenantFixture
corpusVersion
environmentVersion
expectedBehavior
observedBehavior
status
evidenceReferences
cleanupStatus
limitations
```

Không cần đưa nguyên request hoặc response nhạy cảm vào mọi báo cáo. Dùng dữ liệu tổng hợp, marker và tham chiếu artifact có quyền truy cập phù hợp.

Trong CI, các ca cấu trúc có thể chạy nhanh ở mức unit hoặc component. Các ca cần database, browser hoặc worker thật nên được đặt ở tầng tích hợp phù hợp. Không thay toàn bộ tích hợp bằng mock rồi tuyên bố kiểm soát engine đã được kiểm chứng.

Một regression tốt kiểm tra nguyên tắc, không chỉ một chuỗi. Sau khi sửa lỗi ghép SQL, nên xác minh template và binding với nhiều dữ liệu hợp lệ lẫn probe. Sau khi sửa DOM sink, kiểm tra loại node và ngữ cảnh thay vì chỉ tìm một chuỗi đã bị thay thế.

Với corpus sinh ngẫu nhiên, một seed tái hiện được giúp điều tra. Khi tìm thấy ca lỗi, rút gọn payload nhưng giữ nguyên hành vi vi phạm để tạo regression dễ hiểu.

## 15. Ma trận nghiệm thu tổng hợp

| Phạm vi | Ca tối thiểu đại diện | Bằng chứng cần có |
|---|---|---|
| Query giá trị | Bình thường, dấu nháy, chuỗi giống điều kiện | Template, bind và tập kết quả fixture |
| Query cấu trúc | Sort hoặc field ngoài mapping | Từ chối trước sink hoặc chỉ dùng mapping cố định |
| Command | Separator, xuống dòng, option-like input | Executable và argv theo hợp đồng |
| Plain text ra HTML | Markup có marker | DOM text, không tạo cấu trúc ngoài yêu cầu |
| Input object | Sai kiểu hoặc operator ở field scalar | Parser/validator và query object không bị mở rộng |
| Dữ liệu lưu lại | Tạo rồi đọc ở trang/job khác | Liên kết record, consumer và sink |
| Encoding | Trực tiếp, encoding hợp lệ, encoding lỗi | Giá trị qua các lớp đúng hợp đồng |
| Quyền | Cùng payload ở tenant/role khác | Không mở rộng dữ liệu hay thao tác |
| Tài nguyên | Biên kích thước và ngân sách thử | Từ chối hoặc giới hạn tại lớp dự kiến |
| Harness | Baseline và kiểm tra khả năng phát hiện | Điểm quan sát hoạt động, không có PASS giả |
| Cleanup | Ca thành công và ca bị gián đoạn | Dữ liệu thử được quản lý, không tác động ngoài vùng |

Số payload không phải đơn vị đầy đủ của mức bao phủ. Một nghìn biến thể trên một field không thay thế một sink ở job nền chưa được kiểm tra.

Một cách báo cáo hữu ích hơn là số ranh giới hoặc nhánh đã có oracle và bằng chứng, kèm danh sách còn thiếu. Không công bố “100% chống injection” chỉ từ một corpus hữu hạn.

## 16. Bài tập xây dựng kế hoạch kiểm thử

Một ứng dụng nhận ghi chú khách hàng, lưu vào database, hiển thị trên trang người dùng và trang quản trị, đồng thời đưa vào báo cáo được tạo bởi worker nền. Endpoint tìm kiếm có filter sort và đang được bảo vệ bằng một gateway rule.

Hãy xây một kế hoạch:

1. Liệt kê nguồn, phép biến đổi và sink ở từng luồng.
2. Chọn một payload literal có ký tự đặc biệt và một probe theo từng interpreter.
3. Chuẩn bị fixture hai tenant để phát hiện mở rộng phạm vi.
4. Viết oracle riêng cho query binding, sort mapping, DOM và worker.
5. Xác định cách biết dữ liệu đã tới consumer bất đồng bộ.
6. Chỉ ra tín hiệu nào chỉ là quan sát sơ bộ, chưa đủ kết luận.
7. Định nghĩa đối chứng và cách kiểm tra harness.
8. Nêu trạng thái khi gateway chặn nhưng chưa xác minh sink.
9. Thiết kế report và cleanup dựa trên ID của run.
10. Chuyển một phát hiện giả định thành regression kiểm tra ranh giới thay vì blacklist.

Kết quả cần cho phép một người khác tái hiện và đánh giá cùng kết luận mà không phải đoán từ status code hay cảm giác về payload.

## 17. Tài liệu tham khảo

- [OWASP Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Injection_Prevention_Cheat_Sheet.html): phân loại sink và các ranh giới phòng vệ.
- [OWASP SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html): binding dữ liệu và cấu trúc cố định.
- [OWASP WSTG — Reflected Cross Site Scripting](https://owasp.github.io/www-project-web-security-testing-guide/stable/4-Web_Application_Security_Testing/07-Input_Validation_Testing/01-Testing_for_Reflected_Cross_Site_Scripting): kiểm thử theo ngữ cảnh phản chiếu.
- [OWASP Web Security Testing Guide repository](https://github.com/OWASP/wstg): tài liệu kiểm thử và cách định vị phiên bản hướng dẫn.

Kiểm thử payload có giá trị khi nó chứng minh một ranh giới bảo mật được giữ trong luồng dữ liệu thực tế. Payload là phương tiện; oracle, điểm quan sát và giới hạn bằng chứng mới quyết định kết luận có thể nghiệm thu.
