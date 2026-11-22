# Ranh giới giữa mã sinh và mã viết tay

Trong một hệ thống sử dụng ngôn ngữ đặc tả miền (Domain-Specific Language, DSL), compiler hoặc generator thường tạo ra mã nguồn, cấu hình hay artifact từ mô hình khai báo. Những phần mã được tạo tự động được gọi là **mã sinh** (*generated code*). Bên cạnh đó, lập trình viên vẫn cần viết logic riêng, tích hợp dịch vụ, xử lý trường hợp đặc biệt và mở rộng hành vi. Những phần đó là **mã viết tay** (*handwritten code*).

Hai loại mã cần cùng tồn tại trong một dự án mà không làm mất công sức của nhau. Nếu lập trình viên sửa trực tiếp file do generator quản lý, lần sinh mã tiếp theo có thể ghi đè thay đổi. Nếu generator cố gắng bảo toàn mọi chỉnh sửa thủ công trong file đầu ra, nó phải giải quyết xung đột, merge và nhận diện vùng sở hữu rất phức tạp.

Vì vậy, thiết kế sinh mã cần xác định rõ ranh giới: phần nào là nguồn sự thật, file nào do công cụ sở hữu, phần nào lập trình viên được phép mở rộng, và quá trình tái sinh xử lý các thay đổi ra sao. Một ranh giới tốt giúp mã sinh có thể được tạo lại nhiều lần, còn mã viết tay vẫn ổn định, dễ kiểm thử và dễ bảo trì.

## 1. Mã sinh và mã viết tay

### 1.1. Mã sinh là gì?

Mã sinh là đầu ra của một công cụ dựa trên nguồn mô tả khác. Nguồn đó có thể là:

- File DSL.
- Schema dữ liệu.
- Mô hình UML hoặc mô hình miền.
- Định nghĩa API.
- File cấu hình.
- Annotation hoặc metadata.
- Template và tham số build.

Ví dụ, từ mô hình:

~~~text
entity Customer {
    id: CustomerId
    name: String
    email: Optional<String>
}
~~~

Generator có thể tạo lớp Java:

~~~java
public final class Customer {
    private final CustomerId id;
    private final String name;
    private final String email;

    public Customer(CustomerId id, String name, String email) {
        this.id = id;
        this.name = name;
        this.email = email;
    }

    public CustomerId getId() { return id; }
    public String getName() { return name; }
    public String getEmail() { return email; }
}
~~~

Khi mô hình DSL thay đổi, generator có thể tạo lại lớp Customer. Vì vậy, lớp Java này là artifact được quản lý bởi generator.

### 1.2. Mã viết tay là gì?

Mã viết tay là phần do lập trình viên trực tiếp duy trì. Nó thường chứa:

- Quy tắc nghiệp vụ đặc thù chưa được mô hình hóa trong DSL.
- Tích hợp với database, API hoặc hệ thống bên ngoài.
- Xử lý lỗi, logging và telemetry.
- Chính sách bảo mật và quyền truy cập.
- Adapter giữa mô hình sinh và hệ thống hiện có.
- Hành vi mở rộng hoặc tùy biến theo ứng dụng.
- Test, fixture và công cụ hỗ trợ.

Ví dụ, lớp Customer được sinh tự động, còn dịch vụ gửi email được viết tay:

~~~java
public final class CustomerNotificationService {
    private final EmailGateway emailGateway;

    public CustomerNotificationService(EmailGateway emailGateway) {
        this.emailGateway = emailGateway;
    }

    public void sendWelcome(Customer customer) {
        emailGateway.send(customer.getEmail(), "Welcome");
    }
}
~~~

Lớp dịch vụ sử dụng API của Customer nhưng có vòng đời riêng. Khi Customer được sinh lại, logic gửi email vẫn được giữ nguyên miễn là hợp đồng mà nó dùng không thay đổi.

### 1.3. Ranh giới mã là ranh giới sở hữu

Điều quan trọng không chỉ là file nào được tạo tự động. Cần xác định ai sở hữu từng phần:

| Thành phần | Chủ sở hữu chính | Cách thay đổi |
|---|---|---|
| DSL hoặc schema nguồn | Người thiết kế mô hình | Sửa mô hình rồi sinh lại |
| File mã sinh | Generator | Thay đổi nguồn hoặc template được quản lý |
| File mã viết tay | Lập trình viên | Sửa trực tiếp và review như mã ứng dụng |
| API mở rộng | Hợp đồng giữa generator và ứng dụng | Thay đổi có phiên bản và tương thích |
| Build và cấu hình generator | Nhóm dự án | Quản lý tham số, phiên bản và quy trình tái sinh |

Một file có thể chứa cả phần sinh và phần viết tay, nhưng khi đó công cụ phải có quy tắc bảo vệ vùng viết tay. Nếu không có cơ chế rõ ràng, một file nên thuộc về một chủ sở hữu duy nhất.

## 2. Vì sao phải tách mã sinh và mã viết tay?

### 2.1. Tái sinh có thể chạy nhiều lần

Generator thường được chạy lại khi:

- DSL hoặc schema thay đổi.
- Template được sửa.
- Compiler được nâng cấp.
- Một target mới được thêm.
- Build sạch hoặc CI cần tạo lại artifact.

Nếu mã viết tay nằm trong file bị ghi đè, mỗi lần tái sinh có thể làm mất logic. Điều này khiến generator trở thành rủi ro đối với dự án thay vì công cụ hỗ trợ.

### 2.2. Tránh lệch giữa nguồn và đầu ra

Giả sử generator tạo lớp Customer từ schema. Một lập trình viên thêm trường trực tiếp vào Customer.java nhưng không sửa schema. Sau đó:

- Schema không biết trường mới.
- Generator không tạo lại trường đó.
- Lần sinh tiếp theo có thể xóa thay đổi.
- Các module khác không biết nên dùng trường từ schema hay trường được thêm thủ công.

Nguồn sự thật bị chia thành nhiều nơi. Khi cần thay đổi tiếp, nhóm phát triển không biết chỉnh ở đâu.

### 2.3. Giúp review và truy vết thay đổi

Khi file sinh và file viết tay nằm riêng, review có thể xác định:

- Thay đổi nào đến từ mô hình.
- Thay đổi nào đến từ logic ứng dụng.
- Generator version nào tạo ra đầu ra.
- Vì sao một API hoặc lớp được thay đổi.

Điều này cũng giúp tìm nguyên nhân khi build cho ra diff lớn sau khi nâng cấp generator.

### 2.4. Hỗ trợ nhiều ứng dụng dùng chung mô hình

Một schema có thể sinh ra các lớp dùng chung cho nhiều ứng dụng. Mỗi ứng dụng có logic riêng, không nên sửa trực tiếp mã sinh dùng chung chỉ để phục vụ một ứng dụng.

Tách phần mở rộng giúp cùng một mô hình được dùng bởi nhiều consumer với hành vi khác nhau.

### 2.5. Giảm xung đột khi làm việc nhóm

Nếu generator ghi lại hàng trăm file, các chỉnh sửa thủ công cùng nằm trong đó dễ gây merge conflict. Phân vùng đầu ra và extension point giúp giảm số file nhiều người cùng sửa.

## 3. Nguồn sự thật và quy tắc sở hữu

### 3.1. Chọn một nguồn sự thật cho mỗi loại thông tin

Một thuộc tính miền nên có một nơi định nghĩa có thẩm quyền. Ví dụ:

- Kiểu và trường dữ liệu nằm trong schema.
- Logic gửi email nằm trong dịch vụ ứng dụng.
- Template Java nằm trong thư mục template do nhóm generator quản lý.
- Cấu hình target nằm trong build configuration.

Không nên định nghĩa cùng một thuộc tính vừa trong schema vừa trong một lớp viết tay nếu không có quy tắc đồng bộ rõ.

### 3.2. Model-first và code-first

Có hai hướng thường gặp:

**Model-first:** mô hình DSL hoặc schema là nguồn chính; mã được sinh từ mô hình. Khi muốn đổi cấu trúc, người dùng sửa mô hình rồi chạy generator.

**Code-first:** mã nguồn viết tay là nguồn chính; công cụ đọc annotation hoặc reflection để tạo schema, tài liệu hoặc adapter.

Một hệ thống có thể kết hợp hai hướng, nhưng cần chỉ rõ chiều chuyển đổi cho từng artifact. Nếu vừa sinh code từ model vừa suy ngược model từ code mà không có quy tắc ưu tiên, hai nguồn có thể mâu thuẫn.

### 3.3. Không sửa trực tiếp artifact do generator sở hữu

Quy tắc vận hành phổ biến:

1. Xác định file hoặc thư mục generator sở hữu.
2. Sửa DSL, schema hoặc template tương ứng.
3. Chạy lại generator.
4. Review diff của mã sinh.
5. Đặt logic riêng trong extension point hoặc module viết tay.

Nếu cần một thay đổi đặc biệt chỉ dành cho một ứng dụng, nên thêm adapter hoặc lớp mở rộng thay vì sửa file sinh chung.

### 3.4. Metadata nhận diện file sinh

Generator có thể thêm header:

~~~java
// Generated by DslCompiler 2.4.
// Source: model/customer.dsl
// Do not edit this file directly.
~~~

Header giúp lập trình viên và công cụ nhận diện nguồn gốc file. Metadata có thể chứa:

- Tên generator.
- Phiên bản generator.
- File nguồn hoặc định danh mô hình.
- Thời điểm sinh nếu cần truy vết.
- Phiên bản schema hoặc IR.
- Hướng dẫn nơi đặt phần mở rộng.

Không nên chỉ dựa vào header để xác định quyền sở hữu nếu generator còn quản lý manifest hoặc danh sách artifact.

## 4. Tổ chức thư mục đầu ra

### 4.1. Tách thư mục generated và handwritten

Một cấu trúc đơn giản:

~~~text
project/
  model/
    customer.dsl
    order.dsl
  src/
    main/
      java/
        app/
          CustomerService.java
          OrderWorkflow.java
  build/
    generated/
      sources/
        dsl/
          Customer.java
          Order.java
          CustomerRepository.java
~~~

Thư mục build/generated được tạo lại trong build. Mã viết tay nằm trong src/main/java. Generator có thể xóa và tái tạo đầu ra mà không ảnh hưởng logic ứng dụng.

### 4.2. Đưa mã sinh vào source set riêng

Build tool có thể coi thư mục mã sinh là một source root riêng. Ví dụ, cấu hình Gradle có thể thêm thư mục generated vào source set:

~~~kotlin
sourceSets {
    main {
        java.srcDir(layout.buildDirectory.dir("generated/sources/dsl/main"))
    }
}
~~~

Task sinh mã cần chạy trước task compile. Đầu ra của task nên được khai báo rõ để Gradle biết dependency và có thể hỗ trợ incremental build.

### 4.3. Không trộn file sinh vào thư mục mã tay

Nếu generated và handwritten cùng nằm trong một thư mục mà không có manifest hoặc naming convention, người dùng khó biết file nào có thể sửa. Việc clean build cũng có thể xóa nhầm file viết tay.

### 4.4. Khi nào cần commit mã sinh?

Có thể commit generated source nếu:

- Consumer cần đọc mã sinh mà không chạy generator.
- Build môi trường đích không có compiler DSL.
- Review artifact sinh là một phần quy trình.
- Đầu ra cần được phát hành như source package.

Có thể không commit nếu:

- Build luôn có thể tái tạo đầu ra.
- Generated file lớn và gây nhiễu diff.
- Generator và dependency được quản lý ổn định trong build.

Quyết định này cần nhất quán. Dù commit hay không, nguồn sự thật vẫn cần được xác định.

## 5. Các mẫu mở rộng mã sinh

Không phải lúc nào cũng cần sửa mã sinh để bổ sung hành vi. Có nhiều mẫu thiết kế giúp mã viết tay mở rộng API được tạo tự động.

### 5.1. Interface do generator tạo, implementation do người dùng viết

Generator có thể tạo interface:

~~~java
public interface CustomerRepository {
    Optional<Customer> findById(CustomerId id);
    void save(Customer customer);
}
~~~

Ứng dụng tự viết implementation:

~~~java
public final class JdbcCustomerRepository implements CustomerRepository {
    @Override
    public Optional<Customer> findById(CustomerId id) {
        // Truy vấn database
        return Optional.empty();
    }

    @Override
    public void save(Customer customer) {
        // Lưu dữ liệu
    }
}
~~~

Generator sở hữu hợp đồng; ứng dụng sở hữu cách triển khai. Khi hợp đồng thay đổi, compiler sẽ phát hiện implementation nào cần cập nhật.

### 5.2. Lớp cơ sở được sinh và lớp con viết tay

Generator có thể tạo lớp cơ sở:

~~~java
public abstract class GeneratedCustomerRules {
    protected boolean isPreferred(Customer customer) {
        return customer.getTier() == CustomerTier.GOLD;
    }
}
~~~

Ứng dụng mở rộng:

~~~java
public final class CustomerRules extends GeneratedCustomerRules {
    public boolean canReceiveCampaign(Customer customer) {
        return isPreferred(customer) && customer.getEmail() != null;
    }
}
~~~

Khi generator sinh lại GeneratedCustomerRules, CustomerRules vẫn tồn tại.

Mẫu kế thừa phù hợp khi lớp cơ sở được thiết kế để mở rộng và không thay đổi hợp đồng theo cách phá vỡ subclass. Nếu generator thay đổi constructor, phương thức final hoặc visibility, lớp con có thể cần sửa.

### 5.3. Composition và delegation

Một cách ít phụ thuộc kế thừa hơn là bọc đối tượng sinh:

~~~java
public final class CustomerPolicy {
    private final GeneratedCustomerPolicy generated;

    public CustomerPolicy(GeneratedCustomerPolicy generated) {
        this.generated = generated;
    }

    public boolean canApply(Customer customer) {
        return generated.isEligible(customer)
                && customer.hasVerifiedEmail();
    }
}
~~~

Composition giữ logic viết tay trong một lớp riêng và gọi API sinh thông qua delegation. Cách này dễ thay thế implementation và kiểm thử độc lập.

### 5.4. Partial class hoặc partial type

Một số ngôn ngữ, chẳng hạn C#, hỗ trợ partial class để chia một kiểu thành nhiều file. Generator có thể tạo một phần và lập trình viên viết phần còn lại:

~~~csharp
// Generated file
public partial class Customer
{
    public string Name { get; set; }
}
~~~

~~~csharp
// Handwritten file
public partial class Customer
{
    public string DisplayName => Name.Trim();
}
~~~

Hai file được compiler kết hợp thành một kiểu. Tuy nhiên, không phải ngôn ngữ nào cũng hỗ trợ partial type. Java không có partial class theo cơ chế này; trong Java thường dùng interface, kế thừa, composition, helper hoặc delegation.

### 5.5. Callback và hook

Generator có thể tạo điểm gọi callback:

~~~java
public interface CustomerHooks {
    default void beforeSave(Customer customer) {}
    default void afterLoad(Customer customer) {}
}
~~~

Runtime hoặc ứng dụng truyền implementation:

~~~java
public final class AuditCustomerHooks implements CustomerHooks {
    @Override
    public void beforeSave(Customer customer) {
        // Ghi nhận sự kiện kiểm toán
    }
}
~~~

Hook cần có ngữ nghĩa rõ: thời điểm gọi, thứ tự, xử lý exception, thread context và quyền truy cập dữ liệu.

### 5.6. Strategy hoặc provider

Nếu hành vi có thể thay đổi theo ứng dụng, generator có thể phụ thuộc vào interface Strategy:

~~~java
public interface DiscountStrategy {
    Money calculate(Order order);
}
~~~

Phần viết tay cung cấp chiến lược:

~~~java
public final class LoyaltyDiscountStrategy implements DiscountStrategy {
    @Override
    public Money calculate(Order order) {
        // Logic theo chương trình khách hàng thân thiết
        return Money.zero(order.currency());
    }
}
~~~

Generator tạo lời gọi đến abstraction; ứng dụng quyết định implementation.

### 5.7. Annotation và metadata

Generator có thể đọc annotation do lập trình viên thêm vào file nguồn hoặc lớp mở rộng. Annotation phù hợp cho metadata khai báo như tên mapping, validation hoặc cấu hình serialization.

Không nên dùng annotation như một cách giấu logic lớn. Logic nghiệp vụ cần được thể hiện trong lớp hoặc hàm có thể kiểm thử và review.

### 5.8. User region được đánh dấu

Một số generator cho phép vùng do người dùng quản lý trong file sinh:

~~~java
// <user-code id="customer-custom-methods">
// Phần viết tay được giữ lại khi tái sinh.
// </user-code>
~~~

Generator đọc nội dung vùng này trước khi ghi file mới rồi chèn lại vào đúng vị trí.

Mẫu này hữu ích khi một công cụ bên ngoài bắt buộc chỉ tạo một file, nhưng có chi phí bảo trì:

- Marker phải ổn định và duy nhất.
- Vùng phải được parse chính xác.
- Marker bị xóa hoặc lồng nhau sai cần được báo lỗi.
- Đổi tên marker có thể làm mất liên kết với nội dung cũ.
- Merge conflict có thể làm vùng bị nhân đôi hoặc hỏng.

Nếu có thể tách file hoặc dùng interface, các cách đó thường đơn giản hơn việc merge nội dung do generator và người dùng cùng sở hữu.

## 6. Template và extension point của generator

### 6.1. Template là gì?

Template mô tả cách generator tạo artifact từ mô hình. Template có thể là file văn bản với placeholder, template engine hoặc code generator được viết bằng ngôn ngữ lập trình.

Ví dụ template đơn giản:

~~~text
public class {{EntityName}} {
{{#each fields}}
    private final {{Type}} {{name}};
{{/each}}
}
~~~

Template thuộc về nhóm phát triển generator hoặc dự án sở hữu quy trình sinh mã. Người dùng ứng dụng có thể được phép tùy chỉnh template nếu đó là extension point được hỗ trợ.

### 6.2. Phân biệt template với mã sinh

Template là đầu vào của generator; file Java tạo ra là đầu ra. Sửa file Java sinh không tương đương với sửa template. Nếu thay đổi cần áp dụng cho mọi entity, nên sửa template hoặc generator.

### 6.3. Extension point được công bố

Một generator có thể cung cấp:

- Template override.
- Hook trước và sau khi sinh.
- Plugin backend.
- Naming strategy.
- Type mapping.
- Custom annotation processor.
- Interface hoặc abstract class để triển khai.

Extension point cần được tài liệu hóa và version hóa. Một thay đổi nội bộ không nên vô tình phá vỡ extension mà người dùng đang dựa vào.

### 6.4. Thứ tự áp dụng template

Nếu generator hỗ trợ template mặc định và template tùy chỉnh, cần quy định thứ tự:

1. Template mặc định của generator.
2. Template override theo dự án.
3. Hook hoặc post-processor được cho phép.
4. Kiểm tra đầu ra và ghi file.

Không nên để template được chọn ngẫu nhiên theo thứ tự quét thư mục hoặc biến môi trường không được ghi nhận.

### 6.5. Template override và nâng cấp generator

Template tùy chỉnh có thể dựa trên cấu trúc nội bộ của generator. Khi generator nâng cấp, template cũ có thể thiếu placeholder hoặc tạo mã không tương thích.

Nên:

- Ghi phiên bản API template.
- Kiểm tra placeholder bắt buộc.
- Có ví dụ template tối thiểu.
- Cung cấp thông báo khi template cũ không còn hỗ trợ.
- Kiểm thử template override trong build.

## 7. Quy trình tái sinh an toàn

### 7.1. Tái sinh phải có tính lặp lại

Với cùng nguồn mô hình, phiên bản generator và cấu hình, generator nên tạo cùng nội dung đầu ra. Tính xác định giúp:

- Review diff có ý nghĩa.
- Cache hoạt động đúng.
- CI tái tạo được artifact.
- Phát hiện thay đổi ngoài dự kiến.

Không nên để thời gian hiện tại, thứ tự duyệt file ngẫu nhiên hoặc đường dẫn máy cá nhân tạo ra diff không cần thiết.

### 7.2. Không ghi đè vùng ngoài quyền sở hữu

Trước khi ghi, generator nên biết danh sách file do mình quản lý. Có thể dùng manifest:

~~~json
{
  "generator": "DslCompiler",
  "version": "2.4",
  "files": [
    "Customer.java",
    "Order.java",
    "CustomerRepository.java"
  ]
}
~~~

Manifest cho phép xác định file nào cần cập nhật hoặc xóa khi mô hình thay đổi.

### 7.3. Xóa file sinh đã lỗi thời

Nếu entity bị xóa khỏi DSL, file Java tương ứng có thể trở thành stale. Generator cần xóa file cũ nếu nó chắc chắn thuộc quyền sở hữu của mình.

Không nên xóa mọi file trong thư mục output một cách mù quáng nếu thư mục đó có thể chứa file viết tay hoặc artifact của công cụ khác.

### 7.4. Ghi file theo cách nguyên tử

Một lần sinh mã có thể tạo nhiều file. Nếu tiến trình dừng giữa chừng, thư mục đầu ra có thể chứa một phần artifact cũ và một phần artifact mới.

Một cách triển khai an toàn:

1. Sinh toàn bộ file vào thư mục tạm.
2. Kiểm tra đầu ra và tên file.
3. Chỉ khi thành công mới thay thế thư mục hoặc từng file thuộc quyền sở hữu.
4. Cập nhật manifest sau khi ghi hoàn tất.

Việc thay thế cần được thiết kế để tránh mất dữ liệu nếu bước ghi thất bại.

### 7.5. Phát hiện chỉnh sửa thủ công ngoài ý muốn

Generator có thể so sánh hash hoặc nội dung file hiện tại với bản đã sinh trước đó. Nếu file được đánh dấu generated nhưng đã bị sửa thủ công, công cụ có thể:

- Cảnh báo trước khi ghi đè.
- Yêu cầu xác nhận theo chính sách build.
- Ghi bản diff để người dùng di chuyển thay đổi.
- Từ chối tái sinh trong chế độ an toàn.

Trong CI, hành vi thường nên xác định và không phụ thuộc tương tác người dùng. Có thể cấu hình build thất bại khi phát hiện file sinh bị chỉnh tay.

### 7.6. Dry run

Chế độ dry run tính toán những file sẽ được tạo, sửa hoặc xóa mà chưa ghi. Nó giúp review tác động của một thay đổi schema lớn.

Output của dry run có thể gồm:

- Danh sách file mới.
- Danh sách file thay đổi.
- Danh sách file stale.
- Diff dự kiến.
- Cảnh báo về file đã chỉnh thủ công.

## 8. Vùng người dùng và chiến lược merge

### 8.1. Khi nào cần user region?

User region phù hợp khi:

- Hệ sinh thái hoặc framework yêu cầu một file duy nhất.
- Người dùng cần thêm phương thức vào kiểu được sinh.
- Không thể thay đổi kiến trúc sang composition hoặc interface.
- Generator có parser marker ổn định và có thể kiểm thử.

### 8.2. Marker cần định danh ổn định

Mỗi vùng nên có ID duy nhất, không phụ thuộc vị trí dòng:

~~~text
// <user-code id="customer-before-save">
// </user-code>
~~~

Khi template thay đổi, generator tìm theo ID và chèn nội dung cũ vào vùng tương ứng.

### 8.3. Xử lý marker bị thiếu

Nếu vùng cũ có nội dung nhưng template mới không còn marker tương ứng, generator không nên âm thầm bỏ nội dung. Nó có thể:

- Báo lỗi và giữ nguyên file cũ.
- Xuất nội dung vùng bị mất sang file backup.
- Tạo báo cáo migration để người dùng chuyển logic.

### 8.4. Xử lý marker trùng hoặc lồng nhau

Marker trùng ID có thể khiến generator không biết vùng nào là chính. Marker lồng nhau hoặc đóng không đúng thứ tự có thể làm parser nhầm ranh giới.

Nên kiểm tra tính duy nhất, thứ tự mở/đóng và cấu trúc vùng trước khi ghi.

### 8.5. Merge conflict

Nếu hai nhánh cùng sửa một user region, Git vẫn có thể tạo conflict như với mã viết tay. Generator không nên cố giải quyết conflict bằng cách chọn một phiên bản tùy ý.

Người dùng cần giải quyết conflict trước, sau đó chạy lại generator và xác nhận marker còn hợp lệ.

### 8.6. User region không phải nơi đặt mọi logic

Nếu vùng mở rộng ngày càng lớn, nó có thể trở thành một module viết tay nằm trong file sinh. Khi đó nên xem xét chuyển logic ra lớp riêng, dùng interface hoặc composition để làm ranh giới rõ hơn.

## 9. Các mẫu Java để mở rộng mã được sinh

Java không hỗ trợ partial class như C#. Vì vậy, cần chọn cấu trúc phù hợp với hợp đồng mã sinh.

### 9.1. Interface và implementation

Generator tạo interface:

~~~java
public interface OrderValidator {
    ValidationResult validate(Order order);
}
~~~

Ứng dụng triển khai:

~~~java
public final class BusinessOrderValidator implements OrderValidator {
    @Override
    public ValidationResult validate(Order order) {
        if (order.getTotal().isNegative()) {
            return ValidationResult.invalid("Total must not be negative");
        }
        return ValidationResult.valid();
    }
}
~~~

Ưu điểm:

- Không sửa file sinh.
- Có thể thay implementation trong test.
- Nhiều ứng dụng có thể dùng cùng interface với logic riêng.
- Compiler Java kiểm tra hợp đồng khi interface thay đổi.

### 9.2. Kế thừa lớp sinh

Generator tạo lớp có thể mở rộng:

~~~java
public class GeneratedOrderFormatter {
    public String formatId(Order order) {
        return order.getId().toString();
    }
}
~~~

Mã viết tay:

~~~java
public final class OrderFormatter extends GeneratedOrderFormatter {
    public String display(Order order) {
        return "Order #" + formatId(order);
    }
}
~~~

Cần cân nhắc constructor, visibility, final method và khả năng thay đổi superclass khi nâng cấp generator.

### 9.3. Composition

~~~java
public final class OrderService {
    private final GeneratedOrderMapper mapper;
    private final OrderRepository repository;

    public OrderService(
            GeneratedOrderMapper mapper,
            OrderRepository repository) {
        this.mapper = mapper;
        this.repository = repository;
    }

    public void save(OrderInput input) {
        Order order = mapper.toOrder(input);
        repository.save(order);
    }
}
~~~

Composition giảm phụ thuộc vào cấu trúc nội bộ của lớp sinh. Service chỉ dựa vào API công khai.

### 9.4. Decorator

Nếu cần thêm hành vi trước hoặc sau một implementation:

~~~java
public final class AuditingOrderRepository implements OrderRepository {
    private final OrderRepository delegate;
    private final AuditLog auditLog;

    public AuditingOrderRepository(
            OrderRepository delegate,
            AuditLog auditLog) {
        this.delegate = delegate;
        this.auditLog = auditLog;
    }

    @Override
    public void save(Order order) {
        delegate.save(order);
        auditLog.record("order.saved", order.getId());
    }
}
~~~

Decorator cho phép bổ sung logging, caching hoặc kiểm tra mà không sửa implementation sinh.

### 9.5. Adapter

Nếu mã sinh dùng một API khác với hệ thống hiện có, adapter chuyển đổi giữa hai hợp đồng:

~~~java
public final class LegacyCustomerAdapter {
    private final GeneratedCustomer customer;

    public LegacyCustomerAdapter(GeneratedCustomer customer) {
        this.customer = customer;
    }

    public String legacyName() {
        return customer.getDisplayName();
    }
}
~~~

Adapter giúp cô lập thay đổi của generator khỏi phần còn lại của ứng dụng.

## 10. Ranh giới API và tương thích khi generator thay đổi

### 10.1. Generated API là hợp đồng

Mã viết tay thường phụ thuộc vào constructor, method, field, interface và kiểu do generator tạo. Những phần công khai đó tạo thành API của generated code.

Nếu generator đổi tên method hoặc đổi kiểu trả về, các module viết tay có thể không biên dịch được.

### 10.2. Phân loại thay đổi API

| Thay đổi | Ảnh hưởng có thể có |
|---|---|
| Thêm method mới | Thường ít phá vỡ, trừ interface có implementation bên ngoài |
| Xóa method | Có thể làm mã viết tay không biên dịch |
| Đổi tên method | Phá vỡ mọi caller dùng tên cũ |
| Đổi kiểu tham số | Có thể phá vỡ lời gọi |
| Đổi kiểu trả về | Có thể phá vỡ assignment và override |
| Đổi constructor | Có thể phá vỡ code tạo đối tượng |
| Thay đổi visibility | Có thể làm API không còn truy cập được |
| Đổi semantics mà giữ chữ ký | Có thể làm hành vi thay đổi mà compiler không phát hiện |

### 10.3. Semantic compatibility

API có thể giữ nguyên chữ ký nhưng đổi ý nghĩa. Ví dụ, method getTotal trước đây trả tổng trước thuế, sau đó generator đổi thành tổng sau thuế.

Compiler Java không phát hiện được sự thay đổi này. Cần tài liệu, test hợp đồng và versioning để quản lý.

### 10.4. Deprecation

Khi muốn thay method cũ, generator có thể giữ method cũ trong một giai đoạn và đánh dấu deprecated:

~~~java
@Deprecated
public Money total() {
    return grandTotal();
}
~~~

Mã viết tay có thời gian chuyển sang API mới trước khi method cũ bị xóa ở phiên bản major.

### 10.5. Version hóa generated API

Artifact sinh nên ghi nhận:

- Phiên bản DSL hoặc schema.
- Phiên bản generator.
- Phiên bản API mà runtime hỗ trợ.
- Phiên bản template nếu có override.
- Target hoặc nền tảng đầu ra.

Metadata này giúp xác định vì sao hai build tạo ra mã khác nhau và có thể tái tạo artifact cũ khi cần.

## 11. Quy trình build và tái sinh

### 11.1. Thứ tự build

Một pipeline thông thường:

~~~mermaid
flowchart TD
    A["DSL / schema nguồn"] --> B["Chạy generator"]
    B --> C["Generated sources"]
    C --> D["Compile generated + handwritten"]
    E["Handwritten sources"] --> D
    D --> F["Unit và integration tests"]
    F --> G["Package artifact"]
~~~

Generator phải hoàn tất trước khi compiler ngôn ngữ đích biên dịch source set chứa mã sinh.

### 11.2. Đầu vào và đầu ra task

Build tool cần biết:

- File DSL và schema là input.
- Generator binary hoặc plugin là dependency.
- Cấu hình target là input.
- Thư mục generated là output.

Khai báo chính xác giúp build cache và incremental build hoạt động đúng.

### 11.3. Clean build

Clean build xóa output được quản lý rồi tái tạo từ nguồn. Nếu mã viết tay nằm trong output directory, clean có thể xóa nhầm. Vì vậy, thư mục generated nên tách khỏi source root viết tay.

### 11.4. Build cục bộ và CI

Build cục bộ và CI cần dùng cùng phiên bản generator và cùng cấu hình có ảnh hưởng đến đầu ra. Nếu developer dùng generator khác với CI, diff có thể xuất hiện dù nguồn DSL không đổi.

### 11.5. Kiểm tra mã sinh có cập nhật

Nếu generated source được commit, CI có thể chạy generator rồi kiểm tra working tree có thay đổi hay không. Nếu có, repository đang chứa output chưa đồng bộ với nguồn.

Nếu generated source không được commit, CI cần sinh lại trước khi compile và test.

## 12. Version control và review

### 12.1. Commit nguồn và artifact

Khi commit generated source, nên commit cả nguồn DSL và metadata cần thiết để tái tạo. Không nên chỉ commit file sinh mà bỏ nguồn sự thật.

### 12.2. Diff mã sinh

Diff có thể lớn khi template hoặc generator version thay đổi. Review nên xác định:

- Thay đổi nào do mô hình nguồn.
- Thay đổi nào do template.
- Thay đổi nào do nâng cấp generator.
- Có file stale bị xóa đúng không.
- Có file viết tay bị tác động không.

### 12.3. Không chỉnh tay để làm diff đẹp

Nếu mã sinh có định dạng khó đọc, nên sửa formatter hoặc template. Chỉnh trực tiếp file output có thể bị mất ở lần sinh tiếp theo.

### 12.4. Merge branch

Hai nhánh có thể thay đổi cùng schema hoặc cùng template. Sau khi merge, cần chạy generator từ trạng thái nguồn đã hợp nhất để tạo một bộ artifact thống nhất.

Không nên merge thủ công các file sinh nếu chúng có thể được tái tạo từ nguồn đã merge.

### 12.5. Review mã viết tay độc lập

Khi mã viết tay nằm riêng, review tập trung vào logic ứng dụng. Generated diff có thể được kiểm tra theo quy trình riêng hoặc xác nhận bằng cách tái sinh.

## 13. Debug lỗi trong mã sinh

### 13.1. Lỗi biên dịch ở file generated

Compiler Java có thể báo lỗi tại một dòng trong file sinh. Người dùng cần truy ngược đến:

- Mô hình DSL tạo ra cấu trúc đó.
- Template đã sinh dòng mã.
- Mã viết tay đang gọi API sinh.

Header và source mapping giúp xác định nguồn.

### 13.2. Source map

Generator có thể lưu metadata ánh xạ đoạn mã Java về node DSL:

~~~text
Generated range: Customer.java, lines 40-44
Source range: model/customer.dsl, lines 8-10
Node: FieldDeclaration(email)
~~~

Khi compiler hoặc runtime báo lỗi, công cụ có thể hiển thị vị trí trong DSL thay vì chỉ dòng mã sinh.

### 13.3. Phân biệt lỗi generator và lỗi model

Nếu đầu ra sai cú pháp với mô hình hợp lệ, có thể là lỗi template hoặc backend. Nếu mô hình vi phạm quy tắc miền, lỗi thuộc nguồn DSL hoặc semantic analyzer.

Nếu mã sinh hợp lệ nhưng mã viết tay gọi sai API, lỗi thuộc phần tích hợp. Phân loại đúng giúp sửa đúng nơi.

### 13.4. Debug runtime

Mã sinh có thể được biên dịch với debug symbol hoặc metadata source map. Runtime có thể báo tên rule, file DSL và node hành động tương ứng.

### 13.5. Giữ mã sinh dễ đọc

Tên biến có ý nghĩa, formatting ổn định và cấu trúc không quá lồng nhau giúp lập trình viên đọc mã sinh khi cần điều tra. Mã sinh không nhất thiết phải tối ưu cho chỉnh sửa thủ công, nhưng nên đủ rõ để debug.

## 14. Kiểm thử ranh giới giữa mã sinh và mã viết tay

### 14.1. Kiểm thử generator

Kiểm tra generator tạo đúng file, chữ ký và cấu trúc dự kiến từ một mô hình đầu vào.

### 14.2. Kiểm thử tái sinh

Chạy generator nhiều lần với cùng input và xác nhận đầu ra ổn định. Kiểm tra rằng file viết tay không bị thay đổi.

### 14.3. Kiểm thử extension point

Nếu generator tạo interface hoặc hook, cần có test cho implementation viết tay và kiểm tra tương thích khi API thay đổi.

### 14.4. Kiểm thử hợp đồng

Consumer viết tay có thể được kiểm thử với generated API. Contract test xác nhận các method, kiểu và semantics mà consumer phụ thuộc.

### 14.5. Kiểm thử clean build

Xóa generated output rồi chạy build từ nguồn. Build cần tái tạo đủ file và biên dịch cùng mã viết tay.

### 14.6. Kiểm thử stale file

Xóa một khai báo khỏi DSL rồi sinh lại. Xác nhận artifact cũ thuộc generator được xóa, trong khi file viết tay không bị xóa.

### 14.7. Kiểm thử khi generator nâng cấp

Chạy generator version mới trên cùng mô hình và review API diff. Test cần phát hiện breaking change và thay đổi semantics.

### 14.8. Kiểm thử source mapping

Tạo một lỗi có thể truy vết từ mã sinh về DSL và xác nhận file, dòng, cột được ánh xạ đúng.

## 15. Những tình huống ranh giới thường gặp

### 15.1. Người dùng sửa file generated

Nếu một thay đổi thủ công cần được giữ lại, hãy xác định nó có phải logic ứng dụng hay thay đổi mô hình. Logic ứng dụng nên chuyển ra extension. Thay đổi mô hình nên được đưa về DSL hoặc schema.

### 15.2. Generator cần tạo một method tùy biến

Nếu method có thể được định nghĩa bằng một hook hoặc strategy, generator nên tạo điểm mở rộng. Nếu method là quy tắc nghiệp vụ riêng, nó nên nằm trong lớp viết tay.

### 15.3. Generated class không có constructor phù hợp

Có thể tạo factory hoặc builder viết tay bao quanh constructor sinh. Nếu nhiều ứng dụng cần cùng cách tạo đối tượng, cân nhắc đưa factory contract vào generator hoặc schema.

### 15.4. Generated API thay đổi

Khi method hoặc kiểu thay đổi, cập nhật consumer viết tay, thêm deprecation nếu cần và version hóa artifact. Không nên sửa file sinh để khôi phục API cũ vì lần tái sinh sẽ xóa thay đổi đó.

### 15.5. Một ứng dụng cần khác biệt so với ứng dụng khác

Không nên fork hoặc sửa mã sinh chung chỉ để phục vụ một consumer nếu có thể dùng strategy, provider, adapter hoặc cấu hình target.

### 15.6. Template tùy chỉnh bị lỗi sau nâng cấp

Template override cần được kiểm tra với phiên bản API template mới. Nếu không tương thích, generator nên dừng với diagnostic cụ thể thay vì sinh file thiếu hoặc sai.

### 15.7. File sinh bị xóa khỏi source control

Nếu generated source được commit, việc xóa file có thể khiến build thất bại nếu generator không chạy trước compile. Build cần thể hiện rõ dependency task và quy tắc tái tạo.

## 16. Bảo mật và độ tin cậy

### 16.1. Mã sinh vẫn là mã thực thi

Generated code có thể truy cập dữ liệu, file, mạng hoặc API. Việc tạo tự động không làm nó trở nên đáng tin mặc định.

### 16.2. Kiểm tra đầu vào của generator

Tên kiểu, tên trường và literal từ DSL cần được validate và escape đúng ngữ cảnh. Nếu đưa trực tiếp vào mã Java hoặc SQL, dữ liệu nguồn có thể làm hỏng cú pháp hoặc tạo injection.

### 16.3. Không thực thi template tùy ý

Template engine có thể có khả năng chạy biểu thức hoặc gọi hàm. Chỉ nạp template từ nguồn được tin cậy và giới hạn capability của template nếu người dùng có thể cung cấp override.

### 16.4. Không để mã viết tay phá vỡ invariant sinh

Extension point nên được thiết kế sao cho logic viết tay không thể tùy ý thay đổi trạng thái nội bộ mà generator hoặc runtime dựa vào. Dùng interface, immutable model và validation giúp giới hạn những thay đổi không hợp lệ.

### 16.5. Kiểm soát dependency

Generator plugin và template package cần được quản lý version, nguồn và quyền. Một plugin không đáng tin có thể chạy mã trong quá trình build.

### 16.6. Tái sinh trong môi trường an toàn

CI nên chạy generator trong môi trường có quyền tối thiểu cần thiết, giới hạn tài nguyên và không cấp secret không cần thiết cho bước sinh mã.

## 17. Ví dụ tổng hợp: sinh model và mở rộng dịch vụ khách hàng

Giả sử DSL định nghĩa:

~~~text
entity Customer {
    id: CustomerId
    name: String
    email: Optional<String>
    tier: CustomerTier
}
~~~

### 17.1. Mã do generator sở hữu

Generator tạo:

~~~java
// Generated by DslCompiler.
// Source: model/customer.dsl.
// Do not edit this file directly.
public final class Customer {
    private final CustomerId id;
    private final String name;
    private final String email;
    private final CustomerTier tier;

    public Customer(
            CustomerId id,
            String name,
            String email,
            CustomerTier tier) {
        this.id = id;
        this.name = name;
        this.email = email;
        this.tier = tier;
    }

    public CustomerId getId() { return id; }
    public String getName() { return name; }
    public String getEmail() { return email; }
    public CustomerTier getTier() { return tier; }
}
~~~

File này được tạo lại khi model thay đổi.

### 17.2. Mã viết tay dùng composition

~~~java
public final class CustomerProfileService {
    private final CustomerRepository repository;
    private final EmailGateway emailGateway;

    public CustomerProfileService(
            CustomerRepository repository,
            EmailGateway emailGateway) {
        this.repository = repository;
        this.emailGateway = emailGateway;
    }

    public void welcome(CustomerId id) {
        Customer customer = repository.findById(id)
                .orElseThrow(() -> new CustomerNotFoundException(id));

        if (customer.getEmail() != null) {
            emailGateway.send(
                    customer.getEmail(),
                    "Welcome " + customer.getName());
        }
    }
}
~~~

Service phụ thuộc vào API công khai của Customer và repository. Nó có thể thay đổi mà không cần sửa file sinh.

### 17.3. Khi model thêm trường

Nếu DSL thêm phoneNumber, generator cập nhật Customer và constructor. Service có thể không cần thay đổi nếu không sử dụng trường mới. Nếu constructor được gọi trực tiếp ở nhiều nơi, những nơi đó có thể cần cập nhật; một factory hoặc builder có thể giảm phụ thuộc vào chữ ký constructor.

### 17.4. Khi logic riêng cần dùng chung

Nếu nhiều service cần quy tắc kiểm tra email, có thể đưa quy tắc đó vào EmailPolicy viết tay hoặc mô hình hóa thành một contract chung. Không nên sao chép logic vào từng file generated.

### 17.5. Tái sinh và review

Quy trình:

1. Sửa customer.dsl nếu cấu trúc miền thay đổi.
2. Chạy generator.
3. Xem diff của Customer.java và những artifact liên quan.
4. Biên dịch cùng mã viết tay.
5. Chạy test cho model, repository và service.
6. Commit nguồn DSL, cấu hình generator và artifact theo chính sách repository.

Không cần sửa trực tiếp Customer.java để giữ logic gửi email; phần đó thuộc CustomerProfileService.

## 18. Checklist thiết kế ranh giới

Khi thiết kế một generator, nhóm phát triển có thể xác định:

| Câu hỏi | Quyết định cần có |
|---|---|
| Nguồn sự thật nằm ở đâu? | DSL, schema, code hay cấu hình |
| File nào generator sở hữu? | Danh sách output hoặc manifest |
| Mã viết tay đặt ở đâu? | Source root riêng hoặc extension module |
| Người dùng mở rộng bằng cách nào? | Interface, composition, subclass, hook hoặc user region |
| Tái sinh xử lý file stale ra sao? | Xóa có kiểm soát và bảo vệ file ngoài quyền sở hữu |
| Phát hiện chỉnh tay thế nào? | Header, hash, manifest hoặc diff |
| API sinh có version không? | Version schema, generator và contract |
| Template tùy chỉnh được hỗ trợ ra sao? | API template và compatibility policy |
| Lỗi sinh mã truy về nguồn thế nào? | Source span hoặc source map |
| Build chạy theo thứ tự nào? | Generator trước compile và test |
| CI xác nhận tính tái tạo ra sao? | Clean build và kiểm tra diff |

## 19. Những sai lầm thường gặp

### 19.1. Sửa trực tiếp file sinh

Thay đổi có thể mất ở lần tái sinh tiếp theo. Hãy chuyển logic sang module viết tay hoặc đưa thay đổi mô hình về nguồn DSL.

### 19.2. Đặt file viết tay trong thư mục bị clean

Clean build có thể xóa nhầm. Generated output và handwritten source cần có vị trí riêng.

### 19.3. Không công bố extension point

Người dùng buộc phải sửa file sinh vì không có cách mở rộng chính thức. Generator nên cung cấp API mở rộng phù hợp với nhu cầu dự kiến.

### 19.4. Tạo quá nhiều user region

Một file có nhiều vùng tùy biến trở nên khó hiểu và khó merge. Nếu logic riêng có cấu trúc đáng kể, nên tách thành lớp hoặc module riêng.

### 19.5. Không quản lý stale file

File sinh từ khai báo đã xóa vẫn tồn tại và có thể được compile hoặc đóng gói. Manifest giúp generator xóa đúng artifact thuộc quyền sở hữu.

### 19.6. Không kiểm tra tính lặp lại

Generator tạo diff khác nhau giữa các lần chạy khiến review và cache khó tin cậy. Đầu ra cần xác định với cùng input và cấu hình.

### 19.7. Thay đổi generated API không có lộ trình

Một thay đổi chữ ký có thể làm hỏng nhiều module viết tay. Cần deprecation, versioning và kiểm thử consumer.

### 19.8. Coi mã sinh không cần review

Mã sinh có thể chứa lỗi template, ánh xạ kiểu hoặc injection. Nó vẫn cần được kiểm thử và kiểm soát như một artifact phần mềm.

## 20. Quy trình xây dựng và vận hành generator

Một quy trình thực tế có thể gồm:

1. **Xác định nguồn sự thật:** chọn DSL, schema hoặc code làm nơi định nghĩa từng loại thông tin.
2. **Xác định quyền sở hữu:** liệt kê thư mục và file do generator quản lý.
3. **Thiết kế API sinh:** tạo interface, kiểu dữ liệu và hợp đồng ổn định.
4. **Thiết kế extension point:** chọn composition, delegation, subclass, hook hoặc template override.
5. **Tổ chức source root:** tách generated output khỏi mã viết tay.
6. **Gắn metadata:** header, manifest và version.
7. **Triển khai tái sinh an toàn:** dry run, ghi tạm, kiểm tra và thay thế có kiểm soát.
8. **Quản lý file stale:** chỉ xóa artifact đã được xác nhận thuộc generator.
9. **Tích hợp build:** khai báo input/output và dependency task.
10. **Kiểm thử ranh giới:** tái sinh, clean build, extension contract và source mapping.
11. **Version hóa API:** deprecation và lộ trình breaking change.
12. **Theo dõi CI:** bảo đảm artifact tái tạo được và mã viết tay không bị ghi đè.

## 21. Câu hỏi tự đánh giá

1. Mã sinh và mã viết tay khác nhau ở quyền sở hữu và vòng đời như thế nào?
2. Vì sao sửa trực tiếp file generated dễ làm mất thay đổi?
3. Nguồn sự thật có vai trò gì khi DSL và mã nguồn cùng tồn tại?
4. Vì sao nên đặt generated output trong thư mục riêng?
5. Interface, composition và inheritance hỗ trợ mở rộng mã sinh ra sao?
6. Java có partial class không? Có thể dùng mẫu nào thay thế?
7. User region cần những quy tắc marker và merge nào?
8. Manifest giúp quản lý file stale như thế nào?
9. Vì sao generator cần tính xác định và ghi file an toàn?
10. Khi generated API thay đổi, deprecation và versioning giúp gì?
11. Build cần tổ chức task sinh mã và compile theo thứ tự nào?
12. Làm thế nào để xác nhận tái sinh không ghi đè mã viết tay?

## Kết luận

Ranh giới giữa mã sinh và mã viết tay là ranh giới về nguồn sự thật, quyền sở hữu và vòng đời. Mã sinh nên được tạo lại từ DSL, schema hoặc template; mã viết tay nên nằm trong những phần mở rộng có hợp đồng rõ ràng. Tách thư mục, dùng manifest và header, thiết kế interface hoặc composition, quản lý template và kiểm soát tái sinh giúp bảo vệ logic ứng dụng qua nhiều lần cập nhật.

Một generator đáng tin cậy phải tạo đầu ra xác định, ghi file có kiểm soát, phát hiện file bị sửa ngoài quyền sở hữu, quản lý artifact stale và giữ liên kết với nguồn. Generated API cũng cần được version hóa và kiểm thử cùng consumer viết tay. Khi những quy tắc này được thiết kế ngay từ đầu, nhóm phát triển có thể thay đổi mô hình và tái sinh mã thường xuyên mà không làm mất phần logic do con người duy trì.
