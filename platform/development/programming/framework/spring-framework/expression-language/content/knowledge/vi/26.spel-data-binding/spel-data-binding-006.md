# Auto-grow nested paths và collection

Trong Spring Expression Language (SpEL), một biểu thức có thể truy cập property lồng nhau hoặc phần tử collection theo đường dẫn, ví dụ **customer.address.city** hay **items[3].name**. Nếu object trung gian đang null hoặc chỉ số truy cập nằm ngoài phạm vi hiện tại, thao tác thông thường có thể thất bại khi đánh giá.

SpEL cung cấp hai tùy chọn trong **SpelParserConfiguration** để hỗ trợ những tình huống này:

- **autoGrowNullReferences**: tự khởi tạo một object trung gian khi đường dẫn property gặp tham chiếu null và SpEL có đủ thông tin để tạo instance.
- **autoGrowCollections**: tự mở rộng collection khi truy cập một chỉ số vượt quá kích thước hiện tại, trong giới hạn được cấu hình.

Hai tùy chọn này giúp đơn giản hóa data binding và cập nhật object graph. Tuy nhiên, chúng có thể làm thay đổi dữ liệu ngay trong lúc đánh giá biểu thức. Cần hiểu rõ khi nào object hoặc collection được tạo, điều kiện để mở rộng thành công và giới hạn tài nguyên trước khi bật cho luồng xử lý có dữ liệu không tin cậy.

## 1. Auto-grow trong SpEL là gì?

### 1.1. Vấn đề với nested property null

Giả sử có object Person chứa Address:

~~~java
public class Person {

    private Address address;

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }
}

public class Address {

    private String city;

    public Address() {
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }
}
~~~

Nếu address đang null, biểu thức:

~~~java
address.city
~~~

không thể truy cập city trên một object chưa tồn tại. Khi auto-grow null references bị tắt, việc đánh giá đường dẫn này có thể thất bại do receiver trung gian là null.

Khi bật auto-grow null references, SpEL có thể tạo một Address mới tại vị trí address rồi tiếp tục xử lý property city, nếu kiểu đích và constructor cho phép.

### 1.2. Vấn đề với collection index

Giả sử Person có list địa chỉ:

~~~java
public class Person {

    private List<Address> addresses = new ArrayList<>();

    public List<Address> getAddresses() {
        return addresses;
    }

    public void setAddresses(List<Address> addresses) {
        this.addresses = addresses;
    }
}
~~~

Nếu list đang rỗng, biểu thức:

~~~java
addresses[2].city
~~~

yêu cầu truy cập phần tử ở index 2, trong khi list chưa có phần tử tại vị trí đó.

Khi auto-grow collections được bật, SpEL có thể mở rộng collection để index cần truy cập nằm trong phạm vi cho phép. Nếu phần tử được tạo ra vẫn null và đường dẫn tiếp tục truy cập property của nó, auto-grow null references có thể tham gia tạo object trung gian nếu SpEL xác định được kiểu phần tử và có thể khởi tạo.

Cần phân biệt hai hành vi: mở rộng collection tạo thêm vị trí; auto-grow null references tạo object tại một vị trí null khi tiếp tục đi qua property path. Bật một tùy chọn không đồng nghĩa tùy chọn còn lại cũng được bật.

### 1.3. Auto-grow có thể làm thay đổi object graph

Auto-grow không chỉ là cách đọc dữ liệu an toàn hơn. Khi SpEL tự tạo object hoặc mở rộng collection, trạng thái của object graph có thể thay đổi trong quá trình evaluate.

Ví dụ, một biểu thức đọc đường dẫn sâu có thể khiến property trung gian được khởi tạo. Một biểu thức ghi có thể vừa tạo object, vừa mở rộng list, rồi mới gán giá trị cuối cùng.

Do đó, hãy xem auto-grow là hành vi cập nhật dữ liệu có chủ đích. Không bật nó chỉ để tránh nhìn thấy null hoặc lỗi index mà chưa xác định rõ tác động lên object.

## 2. Cấu hình auto-grow bằng SpelParserConfiguration

### 2.1. Hai tùy chọn chính

SpelParserConfiguration cho phép cấu hình hành vi tự mở rộng:

~~~java
SpelParserConfiguration configuration =
        new SpelParserConfiguration(
                true,   // autoGrowNullReferences
                true    // autoGrowCollections
        );

ExpressionParser parser =
        new SpelExpressionParser(configuration);
~~~

Hai giá trị Boolean lần lượt điều khiển việc tự khởi tạo tham chiếu null và tự mở rộng collection.

Nếu không cần auto-grow, hãy dùng cấu hình tắt hoặc parser mặc định phù hợp với phiên bản Spring đang dùng. Cần kiểm tra rõ cấu hình parser của ứng dụng thay vì giả định mọi parser đều có cùng hành vi.

### 2.2. Giới hạn kích thước tự mở rộng

Có thể cấu hình giới hạn kích thước tối đa cho thao tác auto-grow:

~~~java
SpelParserConfiguration configuration =
        new SpelParserConfiguration(
                true,
                true,
                256
        );

ExpressionParser parser =
        new SpelExpressionParser(configuration);
~~~

Tham số thứ ba là **maximumAutoGrowSize**. Nó giới hạn mức mở rộng mà SpEL cho phép trong các thao tác auto-grow được hỗ trợ.

Con số 256 chỉ là ví dụ. Hãy chọn ngưỡng theo cấu trúc dữ liệu, dung lượng bộ nhớ và nhu cầu nghiệp vụ. Không nên dùng một giới hạn lớn tùy tiện, đặc biệt khi index hoặc biểu thức có thể đến từ người dùng.

Giới hạn này không phải giới hạn chung cho mọi collection được tạo sẵn, mọi inline list/map hoặc mọi array construction trong SpEL. Ứng dụng vẫn cần validate kích thước dữ liệu đầu vào riêng.

### 2.3. Tạo parser với cấu hình nhất quán

Ví dụ đầy đủ:

~~~java
SpelParserConfiguration configuration =
        new SpelParserConfiguration(
                true,
                true,
                256
        );

ExpressionParser parser =
        new SpelExpressionParser(configuration);

StandardEvaluationContext context =
        new StandardEvaluationContext(person);

Expression expression =
        parser.parseExpression("address.city");

expression.setValue(context, "Hanoi");
~~~

Trong ví dụ, parser bật cả hai tính năng và giới hạn auto-grow ở mức 256. Khi đường dẫn gặp address null, SpEL có thể khởi tạo Address rồi ghi city nếu các điều kiện khởi tạo và ghi property đều đáp ứng.

Parser mang cấu hình được tạo ra. Nếu một nhóm expression cần chính sách khác, hãy tạo parser với cấu hình phù hợp cho nhóm đó thay vì thay đổi chính sách một cách tùy tiện giữa các request.

## 3. Auto-grow null references trên nested paths

### 3.1. Tự tạo object trung gian

Giả sử object graph có nhiều cấp:

~~~java
public class Employee {

    private Profile profile;

    public Profile getProfile() {
        return profile;
    }

    public void setProfile(Profile profile) {
        this.profile = profile;
    }
}

public class Profile {

    private Contact contact;

    public Profile() {
    }

    public Contact getContact() {
        return contact;
    }

    public void setContact(Contact contact) {
        this.contact = contact;
    }
}

public class Contact {

    private String email;

    public Contact() {
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
~~~

Nếu profile và contact đều null, biểu thức:

~~~java
profile.contact.email
~~~

có thể yêu cầu tạo hai object trung gian khi auto-grow null references được bật và SpEL có thể xác định kiểu của từng property.

Khi gán:

~~~java
parser.parseExpression("profile.contact.email")
        .setValue(context, "employee@example.com");
~~~

SpEL có thể tạo Profile, tiếp tục tạo Contact, sau đó gán email.

### 3.2. Điều kiện để khởi tạo thành công

Auto-grow null references cần đủ thông tin để tạo instance cho property đang null. Trong trường hợp thông thường, kiểu property phải xác định được và có constructor mặc định phù hợp để SpEL gọi.

Việc khởi tạo có thể thất bại nếu:

- Kiểu property không thể xác định.
- Không có constructor mặc định phù hợp.
- Constructor không thể truy cập trong runtime hiện tại.
- Kiểu là interface hoặc abstract class mà không có cách tạo implementation cụ thể.
- Constructor ném exception.
- Property không thể ghi lại instance vừa tạo theo accessor đang sử dụng.

Ví dụ, một property khai báo kiểu interface:

~~~java
private AddressProvider addressProvider;
~~~

SpEL không thể tự suy ra implementation cụ thể chỉ từ interface nếu không có cơ chế tạo instance phù hợp. Hãy khởi tạo implementation trong Java hoặc cung cấp một object đã được tạo sẵn.

### 3.3. Constructor mặc định và side effect

Không nên đặt logic nặng hoặc side effect trong constructor của các kiểu có thể được auto-grow. Một thao tác đọc hoặc ghi expression có thể vô tình kích hoạt constructor khi đường dẫn gặp null.

Constructor của object trung gian nên nhẹ, xác định và không thực hiện I/O. Nếu khởi tạo cần dependency, cấu hình phức tạp hoặc truy cập service, hãy tạo object trong Java rồi gán vào graph trước khi đánh giá SpEL.

### 3.4. Auto-grow không thay thế validation

Việc tạo object trung gian chỉ giúp đường dẫn có object để tiếp tục truy cập. Nó không bảo đảm object mới có dữ liệu nghiệp vụ hợp lệ.

Ví dụ, tạo Address mới có thể để city, district và postalCode đều null. Ứng dụng vẫn cần validate các trường bắt buộc trước khi lưu hoặc dùng object trong nghiệp vụ.

Không xem việc auto-grow thành công là bằng chứng rằng request đã hợp lệ.

## 4. Auto-grow collection

### 4.1. Mở rộng list khi index vượt kích thước

Giả sử list ban đầu có một phần tử:

~~~java
List<String> tags =
        new ArrayList<>(List.of("spring"));
~~~

Khi truy cập index lớn hơn index cuối cùng hiện có, auto-grow collections có thể mở rộng list để vị trí đó tồn tại trong giới hạn cấu hình.

Ví dụ expression:

~~~java
tags[3]
~~~

Với auto-grow collections được bật, list có thể được mở rộng tới vị trí index 3. Các vị trí mới được khởi tạo theo quy tắc của collection và kiểu phần tử; với phần tử tham chiếu, chúng có thể là null cho đến khi được gán hoặc được auto-grow tiếp như một nested reference.

Không nên giả định các phần tử mới tự có giá trị nghiệp vụ. Nếu cần dữ liệu mặc định cụ thể, hãy tạo và gán chúng rõ ràng.

### 4.2. Gán vào index được mở rộng

Ví dụ root object có list:

~~~java
public class FormData {

    private List<String> tags = new ArrayList<>();

    public List<String> getTags() {
        return tags;
    }

    public void setTags(List<String> tags) {
        this.tags = tags;
    }
}
~~~

Với parser bật auto-grow collections:

~~~java
parser.parseExpression("tags[2]")
        .setValue(context, "spel");
~~~

Nếu list có thể thay đổi và index nằm trong giới hạn auto-grow, SpEL có thể mở rộng list rồi gán giá trị tại vị trí 2.

Kết quả là list có đủ vị trí từ index 0 đến index 2. Các phần tử trước đó được giữ nguyên; những vị trí được thêm có thể mang giá trị null tùy kiểu và cơ chế mở rộng.

### 4.3. List bất biến hoặc không hỗ trợ mở rộng

Auto-grow cần một collection có thể thay đổi theo cách mà SpEL sử dụng. Các collection bất biến hoặc không hỗ trợ thêm phần tử có thể khiến thao tác thất bại.

Ví dụ:

~~~java
List<String> tags = List.of("spring");
~~~

List tạo bởi List.of không hỗ trợ add. Nếu SpEL cần mở rộng nó, thao tác không thể hoàn tất bình thường.

Khi cần auto-grow, hãy dùng implementation mutable như ArrayList hoặc chuẩn bị collection có khả năng thay đổi phù hợp. Nếu dữ liệu cần bất biến, hãy tạo bản copy mutable trong giai đoạn binding rồi chuyển thành cấu trúc bất biến sau validation.

### 4.4. Index âm và index quá lớn

Auto-grow không làm cho index âm trở nên hợp lệ. Index âm vẫn là truy cập ngoài phạm vi và có thể gây lỗi khi evaluate.

Index quá lớn cũng cần bị giới hạn. Nếu vượt maximumAutoGrowSize, SpEL từ chối thao tác auto-grow tương ứng thay vì mở rộng không giới hạn.

Hãy validate index từ dữ liệu người dùng trước khi đánh giá. Giới hạn parser là lớp bảo vệ bổ sung, không thay thế validation ở API hoặc service.

## 5. Phân biệt collection index với Map key

List và array dùng index theo vị trí; Map dùng key để tìm entry.

Ví dụ:

~~~java
items[2]
settings['theme']
~~~

Auto-grow collections liên quan tới hành vi mở rộng collection theo index. Không nên suy luận rằng một key chưa tồn tại trong Map sẽ tự động tạo entry mới chỉ vì auto-grow collections đang bật.

Với Map, nếu cần thêm key, hãy dùng thao tác ghi phù hợp và bảo đảm Map có thể thay đổi:

~~~java
parser.parseExpression("settings['theme']")
        .setValue(context, "dark");
~~~

Khả năng ghi phụ thuộc PropertyAccessor/indexer và implementation Map. Một Map bất biến hoặc không cho phép thêm key có thể khiến thao tác thất bại.

Nếu cần khởi tạo một Map hoặc giá trị lồng nhau, hãy xác định rõ Map được tạo ở đâu và kiểu value nào được phép tạo. Auto-grow null references không đồng nghĩa SpEL có thể tự suy ra mọi kiểu value từ một key Map chưa tồn tại.

## 6. Auto-grow và array

Array Java có kích thước cố định theo instance. Vì vậy, cần phân biệt array với List khi thiết kế data binding.

Collection như ArrayList có thể tăng kích thước bằng cách thêm phần tử. Array không có thao tác add để tự tăng chiều dài; nếu một thao tác cần mở rộng array, SpEL phải có khả năng tạo array thay thế và cập nhật lại property chứa array. Điều này phụ thuộc target, property có thể ghi và hỗ trợ của phiên bản Spring đang dùng.

Không nên dựa vào giả định rằng mọi array đều tự mở rộng giống ArrayList. Với dữ liệu đầu vào quan trọng, hãy kiểm thử riêng array và collection trên đúng phiên bản Spring. Nếu cần kích thước động, List thường là lựa chọn rõ ràng hơn.

## 7. Kết hợp auto-grow với data binding

### 7.1. Binding đường dẫn nested property

Một trường form có thể ánh xạ vào property lồng nhau:

~~~java
address.city
~~~

Nếu address đang null, auto-grow null references có thể tạo object trung gian khi parser được cấu hình phù hợp. Điều này giúp binder hoặc expression cập nhật object graph mà không cần khởi tạo thủ công từng cấp trước đó.

Tuy nhiên, việc binder có dùng cùng parser và cấu hình SpEL hay không phụ thuộc thành phần tích hợp. Không nên giả định mọi thao tác binding của Spring MVC đều tự động dùng cấu hình parser riêng mà ứng dụng tạo ra.

Hãy kiểm tra đúng điểm tích hợp: SpEL parser, DataBinder, WebDataBinder hoặc framework component đang thực hiện binding.

### 7.2. Chuẩn bị object graph trước khi bind

Trong nhiều trường hợp, cách dễ kiểm soát hơn là khởi tạo nested object ở constructor hoặc factory:

~~~java
public class RegistrationForm {

    private Address address = new Address();

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }
}
~~~

Khi object graph đã có sẵn, biểu thức không cần tự tạo address. Điều này giúp giảm phụ thuộc vào auto-grow và làm rõ trạng thái ban đầu của form.

Dùng auto-grow khi nó thực sự giúp đơn giản hóa cấu trúc dữ liệu, không dùng như cách che giấu việc object graph chưa được thiết kế rõ ràng.

### 7.3. Kiểm tra sau binding

Sau khi binding hoàn tất, cần kiểm tra:

- Các object trung gian có được tạo đúng kiểu không.
- Collection có số phần tử nằm trong giới hạn không.
- Phần tử được thêm có giá trị mặc định đúng không.
- Các field bắt buộc đã có giá trị chưa.
- Có dữ liệu thừa do index người dùng gửi lên không.
- Có lỗi binding hoặc lỗi chuyển đổi nào được ghi nhận không.

Auto-grow chỉ giải quyết cấu trúc đường dẫn; validation vẫn là bước riêng.

## 8. Giới hạn tài nguyên và an toàn

### 8.1. Rủi ro cấp phát quá lớn

Một expression ngắn có thể yêu cầu index rất lớn:

~~~java
items[100000000]
~~~

Nếu auto-grow được bật mà không có giới hạn phù hợp, thao tác có thể tiêu thụ nhiều bộ nhớ hoặc làm request thất bại.

Luôn cấu hình maximumAutoGrowSize phù hợp và validate index trước khi đánh giá. Không dùng giới hạn tối đa của kiểu int hoặc một ngưỡng quá lớn chỉ để tránh lỗi.

### 8.2. Kiểm soát độ sâu nested paths

Một đường dẫn nhiều cấp có thể tạo nhiều object trung gian. Hãy giới hạn cấu trúc đầu vào và số cấp mà biểu thức được phép truy cập.

Với expression do người dùng cung cấp, không cho phép truy cập tùy ý vào object graph lớn. Chỉ cung cấp DTO hoặc root object nhỏ, có property cần thiết.

### 8.3. Auto-grow có thể tạo side effect khi đọc

Nếu auto-grow null references hoặc collections được bật, một expression tưởng như chỉ đọc có thể làm object graph thay đổi khi truy cập đường dẫn cần mở rộng.

Vì vậy:

- Không dùng parser auto-grow cho biểu thức chỉ đọc nếu không có nhu cầu rõ ràng.
- Tách context đọc và context ghi nếu ứng dụng có hai loại use case khác nhau.
- Không chia sẻ object đang được auto-grow giữa các request đồng thời nếu không có đồng bộ.
- Chỉ đánh giá trên object có vòng đời và quyền thay đổi phù hợp.
- Kiểm thử cả trạng thái trước và sau khi evaluate.

### 8.4. Không cấp quyền rộng cho expression không tin cậy

Auto-grow là một khả năng thao tác dữ liệu, không phải cơ chế sandbox. Nếu expression không tin cậy còn có thể gọi method, truy cập bean hoặc tạo object tùy ý, rủi ro lớn hơn nhiều so với việc mở rộng list.

Hãy giới hạn root object, property accessor, method resolver, bean resolver và type locator theo nhu cầu. Không cho phép người dùng điều khiển source expression tùy ý trong một context có quyền rộng.

## 9. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Nested path vẫn lỗi khi property null | autoGrowNullReferences đang tắt | Bật tùy chọn nếu nghiệp vụ cho phép hoặc khởi tạo object trong Java |
| Không tạo được object trung gian | Không có constructor phù hợp hoặc kiểu không xác định | Dùng kiểu cụ thể, constructor mặc định có thể truy cập hoặc khởi tạo trước |
| List không mở rộng | autoGrowCollections đang tắt | Cấu hình parser phù hợp |
| List mở rộng thất bại | Collection bất biến hoặc không hỗ trợ add | Dùng collection mutable hoặc tạo bản copy |
| Index âm gây lỗi | Index không hợp lệ; auto-grow không xử lý index âm | Validate index trước khi evaluate |
| Index quá lớn bị từ chối | Vượt maximumAutoGrowSize | Kiểm tra dữ liệu và chọn giới hạn phù hợp |
| Map key chưa tồn tại không tự tạo value | Map key lookup khác collection index growth | Ghi key rõ ràng hoặc chuẩn bị value trong Java |
| Object mới có field null | Auto-grow chỉ tạo cấu trúc, không điền dữ liệu nghiệp vụ | Validate và gán giá trị cần thiết |
| Kết quả đọc làm thay đổi object | Auto-grow đã tạo object hoặc mở rộng collection | Dùng parser không auto-grow cho luồng đọc |
| Hành vi array khác List | Array có kích thước cố định và cách thay thế phụ thuộc target | Kiểm thử riêng hoặc dùng List cho dữ liệu động |

## 10. Ví dụ hoàn chỉnh

Ví dụ dưới đây minh họa tạo nested object và mở rộng list trong một form:

~~~java
public class Address {

    private String city;

    public Address() {
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }
}

public class RegistrationForm {

    private Address address;
    private List<String> tags = new ArrayList<>();

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }

    public List<String> getTags() {
        return tags;
    }

    public void setTags(List<String> tags) {
        this.tags = tags;
    }
}
~~~

Cấu hình parser:

~~~java
SpelParserConfiguration configuration =
        new SpelParserConfiguration(
                true,
                true,
                32
        );

ExpressionParser parser =
        new SpelExpressionParser(configuration);

RegistrationForm form = new RegistrationForm();

StandardEvaluationContext context =
        new StandardEvaluationContext(form);
~~~

Gán nested property:

~~~java
parser.parseExpression("address.city")
        .setValue(context, "Hanoi");
~~~

Gán phần tử ở index 2:

~~~java
parser.parseExpression("tags[2]")
        .setValue(context, "spring");
~~~

Sau các thao tác trên, address có thể được tạo và chứa city là Hanoi; tags được mở rộng để có vị trí index 2 và chứa giá trị spring. Các vị trí trước index 2 được giữ hoặc được thêm theo quy tắc mở rộng của collection.

Trong ứng dụng thực tế, hãy validate form sau khi binding, kiểm tra giới hạn kích thước và không dựa vào auto-grow để tạo dữ liệu miền hợp lệ tự động.

## 11. Kiểm thử auto-grow

Nên kiểm thử riêng hai tùy chọn và các giới hạn:

~~~java
SpelParserConfiguration configuration =
        new SpelParserConfiguration(true, true, 16);

ExpressionParser parser =
        new SpelExpressionParser(configuration);

RegistrationForm form = new RegistrationForm();

StandardEvaluationContext context =
        new StandardEvaluationContext(form);

parser.parseExpression("address.city")
        .setValue(context, "Hanoi");

assertNotNull(form.getAddress());
assertEquals("Hanoi", form.getAddress().getCity());

parser.parseExpression("tags[2]")
        .setValue(context, "spring");

assertEquals("spring", form.getTags().get(2));
~~~

Các trường hợp nên có trong bộ test:

- Auto-grow null references bật và tắt.
- Auto-grow collections bật và tắt.
- Nested path có một hoặc nhiều cấp null.
- Kiểu trung gian có và không có constructor mặc định.
- Property kiểu interface hoặc abstract.
- Collection rỗng và collection đã có phần tử.
- Index bằng vị trí kế tiếp, index lớn hơn giới hạn và index âm.
- Collection mutable và immutable.
- Map key chưa tồn tại.
- Đánh giá chỉ đọc và setValue.
- Object graph trước/sau evaluate.
- Hai request đánh giá trên hai object riêng biệt.

Với giới hạn auto-grow, kiểm thử cả trường hợp sát ngưỡng và vượt ngưỡng. Không phụ thuộc vào thông báo lỗi nội bộ nếu message không phải một phần hợp đồng ứng dụng; hãy xác nhận hành vi và loại exception phù hợp với phiên bản Spring đang sử dụng.

## 12. Tổng kết

SpEL hỗ trợ tự mở rộng đường dẫn dữ liệu qua hai tùy chọn trong SpelParserConfiguration:

- **autoGrowNullReferences** tạo object trung gian khi property path gặp null và kiểu đó có thể được khởi tạo.
- **autoGrowCollections** mở rộng collection khi truy cập index vượt kích thước hiện tại.
- **maximumAutoGrowSize** giới hạn mức auto-grow được phép.

Auto-grow hữu ích cho data binding và cập nhật nested object graph, nhưng có thể làm thay đổi dữ liệu ngay cả trong biểu thức tưởng như chỉ đọc. Hãy dùng constructor phù hợp, collection mutable, giới hạn kích thước, validate sau binding và kiểm thử riêng List, Map, array cùng nested path.

Nếu object graph có quy tắc khởi tạo phức tạp, cần dependency injection hoặc có side effect, hãy chuẩn bị object trong Java thay vì để SpEL tự tạo. Chỉ bật auto-grow ở những luồng thực sự cần và kiểm soát rõ dữ liệu cùng quyền mà expression được phép sử dụng.