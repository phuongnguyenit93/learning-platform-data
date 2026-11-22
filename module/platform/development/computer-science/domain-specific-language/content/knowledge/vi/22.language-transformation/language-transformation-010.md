# Tương thích ngược

## 1. Tương thích ngược là gì?

Tương thích ngược (backward compatibility) là khả năng một phiên bản mới tiếp tục hỗ trợ những chương trình, dữ liệu, giao diện hoặc artifact đã được tạo bằng phiên bản cũ theo một hợp đồng đã công bố. Khi một DSL phát triển, người dùng thường có nhiều tệp quy tắc, cấu hình, schema và mã sinh đang chạy trong môi trường khác nhau. Nếu mỗi lần nâng cấp ngôn ngữ đều buộc họ sửa toàn bộ nội dung cũ, chi phí bảo trì và rủi ro triển khai sẽ tăng cao.

Ví dụ, phiên bản 1 của DSL cho phép:

~~~text
rule large-order {
    when order.total > 1000000
    then requireReview(order.id)
}
~~~

Ở phiên bản 2, nhóm phát triển muốn đổi tên hàm thành requireManualReview. Một hệ thống tương thích ngược có thể tiếp tục hiểu tên cũ trong một khoảng thời gian:

~~~text
rule large-order {
    when order.total > 1000000
    then requireReview(order.id)
}
~~~

hoặc cung cấp alias tương thích để chương trình cũ vẫn chạy:

~~~text
function requireReview(orderId) {
    return requireManualReview(orderId);
}
~~~

Tương thích ngược không có nghĩa một sản phẩm không bao giờ được thay đổi. Nó có nghĩa thay đổi được quản lý theo chính sách rõ ràng: phần nào phải tiếp tục hoạt động, phần nào được đánh dấu lỗi thời, phiên bản nào được hỗ trợ và người dùng có thể chuyển đổi ra sao.

Trong một hệ thống biến đổi ngôn ngữ, khái niệm này có phạm vi rộng hơn cú pháp DSL. Nó có thể liên quan tới grammar, ngữ nghĩa, AST, IR, compiler, runtime, API extension, schema, bytecode và mã nguồn được sinh ra.

## 2. Tương thích ngược và tương thích xuôi

Hai khái niệm thường được nhắc cùng nhau:

- **Tương thích ngược:** phiên bản mới có thể tiếp tục xử lý đầu vào hoặc artifact của phiên bản cũ.
- **Tương thích xuôi (forward compatibility):** một thành phần cũ có thể xử lý dữ liệu hoặc đầu vào được tạo bởi phiên bản mới ở mức đã định nghĩa.

Ví dụ, compiler DSL phiên bản 2 đọc được tệp viết theo phiên bản 1 là tương thích ngược. Ngược lại, một công cụ phiên bản 1 đọc được tệp phiên bản 2 mà không bị lỗi, có thể bỏ qua trường mở rộng theo quy tắc, là một dạng tương thích xuôi.

| Tình huống | Phiên bản tạo | Phiên bản sử dụng | Loại tương thích |
|---|---|---|---|
| Compiler mới đọc DSL cũ | DSL v1 | Compiler v2 | Ngược |
| Runtime mới chạy bytecode cũ | Bytecode v1 | Runtime v2 | Ngược |
| Tool cũ bỏ qua trường mới được thêm | Data v2 | Tool v1 | Xuôi, nếu schema cho phép |
| Compiler cũ đọc cú pháp mới chưa biết | DSL v2 | Compiler v1 | Thường không tương thích nếu không có quy tắc mở rộng |

Không nên giả định hỗ trợ tương thích xuôi chỉ vì một parser có thể bỏ qua token lạ. Bỏ qua cú pháp không hiểu có thể làm chương trình bị diễn giải thiếu và gây sai hành vi. Cần quy định chính xác thành phần nào có thể được bỏ qua an toàn.

## 3. Các lớp tương thích trong hệ sinh thái DSL

Một hệ thống DSL có thể có nhiều loại hợp đồng. Tương thích cần được xem xét theo từng lớp:

| Lớp | Điều cần được giữ ổn định | Ví dụ thay đổi phá vỡ |
|---|---|---|
| Source compatibility | Mã DSL cũ vẫn được phân tích hoặc biên dịch | Xóa keyword hoặc đổi cú pháp bắt buộc |
| Semantic compatibility | Cùng chương trình và đầu vào vẫn có ý nghĩa tương đương | Đổi cách tính ngưỡng hoặc thứ tự đánh giá |
| API compatibility | Extension hoặc ứng dụng tích hợp vẫn gọi được API cũ | Xóa method trong compiler SDK |
| Binary compatibility | Bytecode hoặc artifact đã tạo vẫn liên kết được | Đổi instruction hoặc ABI mà không có adapter |
| Data/schema compatibility | Tệp cấu hình và dữ liệu lưu trữ cũ vẫn được đọc | Đổi tên trường mà không hỗ trợ alias |
| Generated-code compatibility | Mã sinh cũ vẫn biên dịch hoặc chạy trong môi trường được hỗ trợ | Đổi signature runtime mà generated source phụ thuộc |
| Operational compatibility | Quy trình triển khai và vận hành cũ vẫn hoạt động | Đổi định dạng cache hoặc giao thức service |

Một thay đổi có thể tương thích ở lớp này nhưng phá vỡ lớp khác. Ví dụ, compiler mới vẫn parse được DSL cũ nhưng sinh ra mã có thứ tự thực thi khác. Khi đó source compatibility được giữ, còn semantic compatibility bị phá vỡ.

Vì vậy, tuyên bố “phiên bản này tương thích ngược” cần nêu rõ phạm vi: tương thích với source, API, bytecode, schema hay toàn bộ artifact trong một khoảng phiên bản cụ thể.

## 4. Xác định hợp đồng cần bảo vệ

Không thể duy trì tương thích nếu nhóm phát triển không biết người dùng đang phụ thuộc vào điều gì. Trước khi thay đổi DSL, cần xác định public contract:

- Cú pháp công khai và từ khóa được hỗ trợ.
- Kiểu dữ liệu, toán tử và quy tắc suy luận kiểu.
- Ý nghĩa của biểu thức, giá trị mặc định và thứ tự thực thi.
- Tên hàm, chữ ký, overload và extension point.
- Định dạng tệp, schema và quy tắc import.
- AST, IR hoặc bytecode nếu chúng được lưu hoặc trao đổi ra ngoài.
- API của compiler, interpreter và runtime.
- Mã lỗi, diagnostic và các định dạng báo cáo mà công cụ bên ngoài đọc.

Một chi tiết nội bộ chỉ trở thành hợp đồng khi người dùng được phép phụ thuộc vào nó hoặc tài liệu cam kết hỗ trợ nó. Ngược lại, nếu AST chỉ là cấu trúc private bên trong compiler và không được serialize, nhóm có thể thay đổi nó tự do hơn.

Nên phân loại thành:

1. **Public stable:** được cam kết tương thích theo chính sách versioning.
2. **Public experimental:** có thể thay đổi với cảnh báo và giới hạn hỗ trợ rõ.
3. **Internal:** không được đảm bảo ổn định và không nên bị ứng dụng bên ngoài phụ thuộc.

Tài liệu API và package boundary cần phản ánh đúng các phân loại này. Không nên vô tình công khai một lớp nội bộ rồi sau đó phải duy trì nó lâu dài chỉ vì người dùng đã bắt đầu phụ thuộc.

## 5. Tương thích ngược của cú pháp DSL

Grammar là một trong những bề mặt tương thích dễ nhận thấy nhất. Một compiler mới thường cần tiếp tục nhận các chương trình hợp lệ đã được viết theo grammar cũ.

Ví dụ, DSL v1 dùng:

~~~text
when order.total > 1000000
~~~

DSL v2 muốn hỗ trợ cú pháp biểu thức rõ hơn:

~~~text
when order.total exceeds money(1000000, VND)
~~~

Có thể giữ cú pháp cũ trong giai đoạn chuyển tiếp và ánh xạ cả hai dạng về cùng một AST:

~~~text
ComparisonExpression
  operator: GREATER_THAN
  left: order.total
  right: money(1000000, VND)
~~~

Cách này giúp các bước semantic analysis và code generation không cần biết biểu thức đến từ cú pháp cũ hay mới.

### 5.1. Thêm cú pháp thường dễ hơn xóa cú pháp

Thêm một keyword hoặc một dạng biểu thức mới thường ít phá vỡ chương trình hiện tại hơn xóa hoặc đổi ý nghĩa cú pháp cũ. Tuy nhiên, ngay cả việc thêm keyword cũng có thể gây xung đột nếu trước đó người dùng được phép đặt identifier cùng tên.

Ví dụ, nếu v2 thêm keyword match nhưng v1 cho phép biến tên match, chương trình cũ:

~~~text
let match = "approved";
~~~

có thể bị parser mới diễn giải khác. Các lựa chọn xử lý gồm:

- Dùng soft keyword chỉ có ý nghĩa ở một vị trí cú pháp cụ thể.
- Tiếp tục cho phép identifier match ở ngữ cảnh cũ.
- Yêu cầu bật language version mới để dùng keyword.
- Cung cấp escape syntax cho identifier trùng keyword.

### 5.2. Không đổi ngữ nghĩa âm thầm

Nguy hiểm hơn việc đổi grammar là giữ cú pháp cũ nhưng đổi ý nghĩa. Ví dụ, v1 hiểu and theo short-circuit, còn v2 đánh giá cả hai vế. Chương trình vẫn parse nhưng có thể phát sinh side effect hoặc lỗi null khác trước.

Thay đổi ngữ nghĩa cần được xem là breaking change nếu nó ảnh hưởng kết quả có thể quan sát. Nếu cần thay đổi, nên cung cấp chế độ ngôn ngữ theo phiên bản hoặc migration rõ ràng.

## 6. Language version và lựa chọn grammar

Một cách kiểm soát tương thích là gắn phiên bản ngôn ngữ vào chương trình:

~~~text
languageVersion = "1";

rule discount {
    when order.total > 1000000
    then applyDiscount(order, 10)
}
~~~

Compiler mới có thể hỗ trợ nhiều language version:

~~~text
Compiler v3
  ├── Parser for DSL v1
  ├── Parser for DSL v2
  └── Parser for DSL v3
~~~

Có thể chọn phiên bản qua:

- Header trong tệp DSL.
- Manifest của project.
- Cấu hình build.
- Metadata gắn với artifact đã biên dịch.

Không nên tự động dùng grammar mới nhất cho mọi tệp cũ nếu ngữ nghĩa đã thay đổi. Phiên bản rõ ràng giúp compiler biết cách parse và diễn giải chương trình.

### 6.1. Default version

Nếu tệp không khai báo phiên bản, compiler cần một chính sách:

- Mặc định về phiên bản cũ nhất được hỗ trợ.
- Mặc định theo cấu hình project.
- Mặc định về phiên bản hiện tại nhưng phát warning.
- Yêu cầu khai báo version trong các dự án mới.

Mỗi lựa chọn có đánh đổi. Mặc định theo project giúp nâng cấp đồng bộ; yêu cầu khai báo version rõ ràng giúp tái lập nhưng tăng cấu hình. Cần tránh để cùng một tệp có ý nghĩa khác nhau chỉ vì chạy trên compiler có default version khác.

## 7. Tương thích AST và IR

AST (Abstract Syntax Tree) và IR (Intermediate Representation) thường là cấu trúc nội bộ giữa parser, semantic analysis và code generator. Nếu chúng chỉ tồn tại trong bộ nhớ của một lần compile, có thể thay đổi linh hoạt. Nếu được serialize, cache lâu dài, dùng trong plugin hoặc trao đổi giữa các process, chúng trở thành định dạng có version và cần chính sách tương thích.

Ví dụ AST v1 biểu diễn phép so sánh:

~~~text
BinaryExpression
  operator: ">"
  left: MemberAccess(order, total)
  right: NumberLiteral(1000000)
~~~

AST v2 có thể chuẩn hóa thành:

~~~text
ComparisonExpression
  kind: GREATER_THAN
  operands:
    - MemberAccess(order, total)
    - MoneyLiteral(1000000, VND)
~~~

Nếu AST v1 được lưu trên đĩa, compiler v2 cần một trong các cách:

1. Tiếp tục đọc định dạng v1.
2. Chuyển đổi AST v1 sang mô hình nội bộ mới.
3. Yêu cầu tái tạo cache từ DSL source.
4. Từ chối cache cũ với thông báo rõ và fallback sang parse lại.

Cache thường có thể bị xóa và tạo lại, nên không nhất thiết phải duy trì tương thích lâu dài. Nhưng phải phân biệt cache nội bộ với artifact được người dùng lưu hoặc trao đổi.

## 8. Tương thích bytecode và runtime

Nếu DSL được biên dịch thành bytecode riêng, instruction set là một hợp đồng giữa compiler và virtual machine.

Ví dụ bytecode v1:

~~~text
LOAD_FIELD order.total
PUSH_NUMBER 1000000
GREATER_THAN
CALL requireReview 1
~~~

Runtime v2 muốn thay GREATER_THAN bằng COMPARE_GT. Có thể:

- Giữ instruction cũ như alias.
- Thêm bước chuyển bytecode v1 sang v2.
- Dùng bytecode version header để chọn decoder.
- Chỉ hỗ trợ một số phiên bản bytecode cũ trong khoảng thời gian đã công bố.

Artifact bytecode nên ghi metadata:

~~~text
artifactVersion: 2
languageVersion: 1
compilerVersion: 3.4
runtimeAbi: 2
~~~

Các phiên bản này có mục đích khác nhau. Language version mô tả cú pháp/ngữ nghĩa DSL; artifact version mô tả định dạng file hoặc bytecode; runtime ABI mô tả hợp đồng gọi giữa artifact và runtime.

Không nên dùng một số version duy nhất để đại diện cho mọi lớp nếu các lớp có vòng đời thay đổi độc lập.

## 9. Tương thích API và extension point

Một DSL thường cho phép ứng dụng chủ đăng ký function, custom type, plugin hoặc provider. Khi API extension thay đổi, extension đã triển khai có thể không biên dịch hoặc không chạy được.

Ví dụ interface v1:

~~~java
public interface DslFunction {
    String name();
    Value invoke(List<Value> arguments);
}
~~~

V2 cần truyền thêm execution context:

~~~java
public interface DslFunctionV2 {
    String name();
    Value invoke(List<Value> arguments, EvaluationContext context);
}
~~~

Có thể hỗ trợ chuyển tiếp bằng adapter:

~~~java
public final class LegacyFunctionAdapter implements DslFunctionV2 {
    private final LegacyDslFunction delegate;

    public LegacyFunctionAdapter(LegacyDslFunction delegate) {
        this.delegate = delegate;
    }

    @Override
    public String name() {
        return delegate.name();
    }

    @Override
    public Value invoke(
            List<Value> arguments,
            EvaluationContext context) {
        return delegate.invoke(arguments);
    }
}
~~~

Adapter cho phép extension cũ tiếp tục hoạt động trong thời gian chuyển tiếp. Tuy nhiên, nếu API mới cung cấp capability hoặc dữ liệu cần thiết cho tính đúng đắn, adapter không nên giả lập một giá trị mặc định nguy hiểm. Cần báo rõ phần chức năng nào của API mới không thể cung cấp qua adapter.

### 9.1. Thêm method vào interface

Trong Java, thêm abstract method vào interface công khai có thể làm implementation của người dùng không còn biên dịch. Default method đôi khi giúp duy trì source và binary compatibility:

~~~java
public interface Rule {
    String name();

    default boolean enabled() {
        return true;
    }
}
~~~

Nhưng default method chỉ an toàn nếu hành vi mặc định có ý nghĩa cho mọi implementation cũ. Nó cũng cần xem xét xung đột với method từ interface khác và side effect.

### 9.2. Giữ adapter và facade nhỏ

Khi đổi API, nên đặt tương thích ở ranh giới:

- Facade duy trì tên API cũ.
- Adapter chuyển kiểu cũ sang kiểu mới.
- Deprecated wrapper chuyển lời gọi sang implementation hiện tại.
- Registry hỗ trợ nhiều phiên bản extension trong thời gian chuyển tiếp.

Không nên để logic cũ và mới phát triển thành hai implementation độc lập lâu dài nếu có thể dùng một implementation chung với adapter mỏng.

## 10. Tương thích schema và dữ liệu cấu hình

DSL cấu hình thường đọc hoặc ghi dữ liệu có cấu trúc như YAML, JSON, XML, HCL hoặc định dạng riêng. Khi schema thay đổi, tệp cũ có thể không còn hợp lệ.

Ví dụ v1:

~~~yaml
retryCount: 3
timeout: 30
~~~

V2 đổi tên trường:

~~~yaml
maxAttempts: 3
timeoutSeconds: 30
~~~

Để đọc cấu hình cũ, loader có thể hỗ trợ alias:

~~~yaml
retryCount: 3
~~~

được ánh xạ thành trường nội bộ maxAttempts. Nếu cả retryCount và maxAttempts cùng xuất hiện, cần quy tắc rõ ràng: báo lỗi xung đột, ưu tiên trường mới hoặc chỉ cho phép khi giá trị bằng nhau.

Các thay đổi schema thường gặp:

- Thêm trường tùy chọn.
- Thêm trường bắt buộc.
- Đổi tên trường.
- Đổi kiểu dữ liệu.
- Đổi giá trị mặc định.
- Chuyển một trường đơn thành danh sách.
- Đổi cách biểu diễn enum hoặc trạng thái.

Thêm trường tùy chọn thường ít phá vỡ hơn thêm trường bắt buộc. Đổi kiểu hoặc giá trị mặc định có thể làm thay đổi hành vi dù file cũ vẫn parse được.

## 11. Tương thích của mã nguồn được sinh

Code generator tạo source code phụ thuộc vào API và runtime mà nó nhắm tới. Nếu runtime thay đổi, mã sinh từ compiler cũ có thể không còn biên dịch.

Ví dụ generated code v1 gọi:

~~~java
RuntimeRules.evaluate(ruleId, context);
~~~

Runtime v2 đổi API:

~~~java
RuleEngine.execute(ruleId, context, executionOptions);
~~~

Các cách duy trì tương thích:

- Giữ method cũ như deprecated wrapper.
- Sinh mã theo runtime target version được chỉ định.
- Có adapter package cho generated source cũ.
- Cung cấp migration tool để cập nhật source.
- Ghi runtime ABI version vào metadata của artifact.

Code generator nên tách language target khỏi runtime target. Một DSL source version có thể được sinh sang nhiều phiên bản API runtime nếu generator có backend tương ứng.

### 11.1. Generated source có phải public contract?

Nếu generated source được người dùng lưu, chỉnh sửa, review hoặc tích hợp với code riêng, nó có thể trở thành một artifact công khai. Khi đó cần cân nhắc:

- Signature và tên class sinh ra.
- Package và import.
- Annotation và interface được implement.
- Cách khởi tạo runtime dependency.
- Cách source map và comment được tạo.

Nếu generated source chỉ là file tạm trong build và có thể tạo lại từ DSL, có thể thay đổi tự do hơn, miễn build contract được giữ.

## 12. Thay đổi tương thích và breaking change

Có thể phân loại thay đổi theo ảnh hưởng:

| Loại thay đổi | Ví dụ | Đánh giá thường gặp |
|---|---|---|
| Thêm cú pháp không xung đột | Thêm toán tử mới ở vị trí không ảnh hưởng identifier cũ | Thường tương thích |
| Thêm API mới | Thêm function hoặc overload không mơ hồ | Thường tương thích |
| Thêm trường tùy chọn | Thêm mô tả vào schema | Thường tương thích nếu reader bỏ qua được |
| Đổi tên API | Xóa tên cũ và chỉ giữ tên mới | Breaking |
| Xóa cú pháp cũ | Bỏ một dạng khai báo đang được dùng | Breaking |
| Đổi giá trị mặc định | Timeout mặc định từ 30 sang 5 giây | Có thể breaking về hành vi |
| Đổi thứ tự đánh giá | Thay short-circuit bằng eager evaluation | Breaking về ngữ nghĩa |
| Đổi kiểu trả về | API trả về Money thay vì Decimal | Có thể breaking source và binary |
| Đổi định dạng bytecode | Thay instruction encoding | Breaking nếu không có reader cũ |

Đánh giá phải dựa trên hợp đồng thực tế, không chỉ dựa vào việc mã có biên dịch hay không. Một thay đổi không làm lỗi compile vẫn có thể làm chương trình chạy khác.

## 13. Versioning và Semantic Versioning

Semantic Versioning (SemVer) thường dùng dạng MAJOR.MINOR.PATCH:

- **MAJOR:** thay đổi không tương thích với hợp đồng đã công bố.
- **MINOR:** thêm chức năng tương thích ngược.
- **PATCH:** sửa lỗi tương thích với hợp đồng hiện tại.

Ví dụ:

~~~text
2.4.1
| | |
| | +-- PATCH: sửa lỗi
| +---- MINOR: thêm chức năng
+------ MAJOR: thay đổi không tương thích
~~~

Với DSL, cần định nghĩa rõ phạm vi SemVer:

- Version của compiler/runtime.
- Version của language specification.
- Version của grammar hoặc schema.
- Version của bytecode/artifact.
- Version của extension API.

Các thành phần này có thể không tăng cùng nhau. Ví dụ compiler v4 có thể hỗ trợ language version 1, 2 và 3; runtime ABI v2 có thể chạy bytecode artifact version 1 và 2.

Không nên gọi một bản phát hành là minor nếu nó đổi hành vi công khai mà người dùng phụ thuộc, kể cả khi chữ ký API không thay đổi.

## 14. Deprecation: cảnh báo trước khi loại bỏ

Deprecation là quá trình công bố một API hoặc cú pháp không còn được khuyến nghị và sẽ được loại bỏ theo lộ trình.

Một quy trình deprecation có thể gồm:

1. Giới thiệu cách mới.
2. Đánh dấu cách cũ là deprecated.
3. Giải thích lý do và cung cấp ví dụ chuyển đổi.
4. Phát warning khi người dùng tiếp tục dùng cú pháp cũ.
5. Theo dõi mức độ sử dụng nếu hệ thống có telemetry phù hợp và được phép.
6. Duy trì trong khoảng thời gian đã công bố.
7. Chỉ loại bỏ trong phiên bản major hoặc mốc tương thích đã quy định.

Ví dụ:

~~~text
@deprecated(
    since = "2.2",
    replacement = "requireManualReview"
)
function requireReview(orderId) {
    return requireManualReview(orderId);
}
~~~

Một warning tốt nêu tên phần tử cũ, phiên bản bắt đầu deprecated, phần tử thay thế và thời điểm dự kiến loại bỏ nếu đã xác định.

Không nên đánh dấu API là deprecated nếu chưa có phương án thay thế hoặc chưa có kế hoạch hỗ trợ. Deprecation kéo dài mà không có lộ trình sẽ khiến người dùng không biết nên hành động thế nào.

## 15. Migration và chuyển đổi chương trình cũ

Khi một thay đổi không thể duy trì vô thời hạn, migration giúp người dùng chuyển sang phiên bản mới.

Các hình thức:

- Hướng dẫn sửa thủ công.
- Công cụ tự động chuyển đổi cú pháp.
- Adapter ở runtime.
- Schema migration.
- Chuyển đổi bytecode hoặc artifact.
- Codemod dựa trên AST.

Ví dụ, đổi hàm requireReview thành requireManualReview. Một codemod có thể:

1. Parse source DSL thành AST.
2. Tìm FunctionCall có tên requireReview.
3. Thay tên function trong node.
4. Giữ nguyên đối số, comment và source metadata.
5. In lại DSL theo formatter.
6. Xuất diff để người dùng review.

Sửa dựa trên AST thường an toàn hơn thay thế chuỗi toàn cục vì nó chỉ đổi đúng vị trí cú pháp. Một phép thay thế văn bản có thể vô tình đổi comment, string literal hoặc tên có tiền tố giống nhau.

### 15.1. Migration cần có tính lặp lại an toàn

Migration nên có khả năng chạy lại mà không làm thay đổi thêm kết quả nếu đã áp dụng. Có thể kiểm tra marker phiên bản hoặc xác định rằng source đã ở dạng mới.

Với dữ liệu quan trọng, migration cần:

- Backup hoặc snapshot trước khi chạy.
- Dry-run để hiển thị thay đổi.
- Báo các trường hợp không tự chuyển được.
- Ghi log kết quả theo từng file.
- Có chiến lược rollback hoặc phục hồi.

Không nên tự động chuyển đổi trường hợp mơ hồ mà không yêu cầu người dùng xác nhận.

## 16. Kiểm thử tương thích ngược

Kiểm thử tương thích cần dùng artifact thực tế của các phiên bản cũ, không chỉ tạo lại test bằng API mới.

### 16.1. Golden corpus

Lưu tập chương trình DSL hợp lệ từ các phiên bản trước. Mỗi lần nâng cấp compiler, chạy parser và semantic checker mới trên corpus đó.

### 16.2. Semantic regression

Chạy cùng bộ đầu vào và so sánh kết quả quan sát được giữa runtime cũ và mới. Với chương trình có side effect, dùng test double hoặc sandbox để ghi lại hành động thay vì gọi hệ thống thật.

### 16.3. API compatibility

Dùng tool kiểm tra public API hoặc biên dịch các extension mẫu đã được build với SDK cũ. Điều này giúp phát hiện thay đổi chữ ký, class hoặc interface.

### 16.4. Binary và artifact compatibility

Lưu bytecode hoặc generated artifact từ compiler cũ rồi chạy trên runtime mới trong ma trận phiên bản được hỗ trợ.

### 16.5. Schema compatibility

Dùng file cấu hình, manifest và schema cũ để kiểm tra reader mới. Kiểm tra cả trường thiếu, trường thừa, giá trị mặc định và alias.

### 16.6. Migration test

Chạy migration trên fixture cũ, xác nhận kết quả mong đợi và chạy lần thứ hai để kiểm tra tính idempotent. Với tool sửa source, kiểm tra comment, whitespace hoặc source mapping được giữ theo yêu cầu.

## 17. Ma trận tương thích

Nếu có nhiều phiên bản compiler, runtime và artifact, cần ghi rõ tổ hợp được hỗ trợ. Ví dụ:

| Compiler | Language version | Artifact version | Runtime hỗ trợ |
|---|---|---|---|
| Compiler 3.x | DSL 1, 2 | 1, 2 | Runtime 2.x |
| Compiler 4.x | DSL 1, 2, 3 | 2, 3 | Runtime 3.x |
| Compiler 5.x | DSL 2, 3, 4 | 3, 4 | Runtime 4.x |

Bảng chỉ là ví dụ minh họa. Dự án thực tế cần xác định thời gian hỗ trợ và các tổ hợp cụ thể. Không nên để người dùng phải thử từng cặp phiên bản mới biết có tương thích hay không.

Ma trận nên bao gồm:

- Compiler và language version.
- Runtime và bytecode version.
- Generated source và runtime API.
- Extension SDK và plugin version.
- Schema và dữ liệu cấu hình.
- Phiên bản formatter hoặc code generator nếu output là artifact được lưu.

## 18. Tài liệu và truyền thông thay đổi

Mỗi bản phát hành nên có release notes phân biệt:

- Tính năng mới.
- Cải tiến không phá vỡ hợp đồng.
- Bug fix có thể ảnh hưởng chương trình trước đây dựa vào hành vi sai.
- API/cú pháp deprecated.
- Breaking changes.
- Hướng dẫn migration.
- Phiên bản cũ còn được hỗ trợ.

Với thay đổi ngữ nghĩa, cần có ví dụ trước và sau cùng giải thích kết quả khác nhau. Với thay đổi API, nên cung cấp đoạn mã thay thế. Với thay đổi schema, nên cung cấp mẫu file mới và công cụ chuyển đổi nếu có thể.

Tài liệu tương thích cần được lưu ở nơi người dùng tìm thấy trước khi nâng cấp, không chỉ trong ghi chú nội bộ sau khi phát hành.

## 19. Những lỗi thiết kế thường gặp

### Đổi ngữ nghĩa nhưng chỉ tăng PATCH

Chương trình cũ vẫn biên dịch nhưng kết quả thay đổi. Đây có thể là breaking change và cần được đánh giá theo hành vi công khai.

### Thêm keyword làm hỏng identifier cũ

Một tên hợp lệ trong phiên bản trước có thể trở thành từ khóa. Dùng soft keyword, language version hoặc escape identifier để quản lý.

### Xóa API trước khi có thời gian chuyển đổi

Extension và ứng dụng tích hợp có thể ngừng biên dịch. Cung cấp wrapper, adapter và deprecation window.

### Không version hóa artifact

Runtime không biết bytecode được tạo bằng instruction set nào. Gắn version vào artifact và xác định các phiên bản runtime hỗ trợ.

### Dựa vào cache như dữ liệu lâu dài

Cache AST hoặc IR cũ có thể không còn phù hợp với compiler mới. Xác định cache có thể tái tạo hay là artifact được cam kết hỗ trợ.

### Migration bằng thay thế chuỗi

Thay thế toàn văn có thể sửa nhầm comment hoặc string literal. Dùng parser, AST và source span cho chuyển đổi cấu trúc.

### Không có corpus chương trình cũ

Chỉ kiểm thử ví dụ mới không phát hiện được chương trình thực tế bị phá vỡ. Lưu golden corpus đại diện cho các phiên bản được hỗ trợ.

### Tuyên bố tương thích không có phạm vi

“Backward compatible” không rõ đang nói về source, runtime, schema hay API. Công bố ma trận và lớp tương thích cụ thể.

## 20. Quy trình quản lý một thay đổi có nguy cơ phá vỡ tương thích

Khi cần thay đổi DSL hoặc runtime, có thể áp dụng quy trình:

1. **Xác định hợp đồng bị ảnh hưởng.** Grammar, semantics, API, schema, bytecode hay generated code?
2. **Tìm người dùng và artifact phụ thuộc.** Xem extension, chương trình lưu trữ, cache và runtime đang dùng.
3. **Phân loại mức độ thay đổi.** Tương thích, deprecated hay breaking.
4. **Chọn chiến lược chuyển tiếp.** Alias, adapter, versioned parser, dual reader hoặc migration tool.
5. **Định nghĩa language/artifact version.** Bảo đảm compiler và runtime biết cách diễn giải đầu vào.
6. **Viết kiểm thử từ phiên bản cũ.** Dùng source, binary và schema thật hoặc fixture đại diện.
7. **Công bố release notes và migration guide.** Nêu phạm vi, thời gian và hành động người dùng cần thực hiện.
8. **Theo dõi giai đoạn deprecation.** Đưa warning rõ ràng và duy trì hỗ trợ theo cam kết.
9. **Loại bỏ theo mốc đã công bố.** Chỉ xóa khi phiên bản và chính sách cho phép.
10. **Giữ lại kiểm thử hồi quy.** Đưa các trường hợp từng gây breaking change vào corpus lâu dài.

## 21. Ví dụ end-to-end: nâng cấp DSL từ v1 lên v2

Giả sử DSL v1 có:

~~~text
languageVersion = "1";

rule approval {
    when order.total > 1000000
    then requireReview(order.id)
}
~~~

DSL v2 muốn:

- Dùng Money literal có đơn vị.
- Đổi tên hàm requireReview.
- Chuẩn hóa cú pháp condition.

Một chương trình v2:

~~~text
languageVersion = "2";

rule approval {
    when order.total exceeds money(1000000, VND)
    then requireManualReview(order.id)
}
~~~

Compiler v2 có thể xử lý source v1 bằng parser v1 và chuyển AST về IR chung:

~~~mermaid
flowchart TD
    A["DSL v1 source"] --> B["Parser v1"]
    C["DSL v2 source"] --> D["Parser v2"]
    B --> E["Versioned AST"]
    D --> E
    E --> F["Common IR"]
    F --> G["Semantic analysis"]
    G --> H["Code generation"]
~~~

Trong bước semantic analysis, compiler có thể ánh xạ requireReview sang implementation hiện tại của requireManualReview. Đồng thời, nó phát warning cho cú pháp hoặc tên đã deprecated.

Người dùng có thể chạy migration tool để:

1. Thêm languageVersion = 2.
2. Chuyển biểu thức so sánh sang cú pháp mới.
3. Đổi tên function call trong AST.
4. Giữ comment và vị trí nguồn.
5. In lại file bằng formatter DSL.
6. Chạy lại parser và test hành vi.

Trong giai đoạn chuyển tiếp, compiler có thể hỗ trợ cả v1 và v2. Sau mốc hỗ trợ đã công bố, phiên bản major tiếp theo có thể loại bỏ v1 nếu migration đã có đủ thời gian và công cụ.

## 22. Kết luận

Tương thích ngược giúp chương trình, dữ liệu và extension được tạo bằng phiên bản cũ tiếp tục hoạt động khi hệ sinh thái DSL phát triển. Nó bao gồm nhiều lớp: source, semantics, API, binary, schema, generated code và vận hành. Giữ mã cũ biên dịch là chưa đủ nếu kết quả hoặc side effect thay đổi ngoài hợp đồng.

Một chiến lược hiệu quả cần xác định public contract, version hóa language và artifact, quản lý deprecation, cung cấp adapter hoặc migration tool và kiểm thử bằng corpus từ các phiên bản cũ. Những thay đổi cú pháp và API nên có giai đoạn chuyển tiếp; thay đổi ngữ nghĩa cần được xem xét cẩn thận vì có thể phá vỡ hành vi dù source vẫn hợp lệ.

Khi phát triển DSL, hãy công bố rõ phiên bản nào đọc được source hoặc artifact nào, phần nào còn được hỗ trợ và người dùng cần làm gì khi nâng cấp. Tương thích ngược được quản lý có chủ đích sẽ giúp ngôn ngữ tiến hóa mà không buộc mọi ứng dụng phải thay đổi cùng lúc.
