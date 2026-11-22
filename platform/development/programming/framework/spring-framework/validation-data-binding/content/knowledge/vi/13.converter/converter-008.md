# Converter có thể tái sử dụng cho phần tử mảng hoặc collection trong Spring

Một **Converter<S, T>** thường mô tả phép chuyển đổi ở cấp một giá trị: từ kiểu nguồn **S** sang kiểu đích **T**. Trong ứng dụng Java, dữ liệu thường đến dưới dạng mảng hoặc collection. Ví dụ, form gửi nhiều chuỗi tag trong khi đối tượng đích muốn giữ **List<Tag>**; hoặc service nhận **List<String>** và cần tạo **Set<Tag>**.

Spring có sẵn các converter cấu trúc cho những trường hợp phổ biến. Khi một **ConversionService** chứa converter **String → Tag** và có converter array/collection tương ứng, Spring có thể dùng converter giá trị đó cho từng phần tử khi chuyển cả mảng hoặc collection. Ta thường chỉ cần viết converter cho kiểu phần tử, không phải viết converter riêng cho mọi cặp **String[] → List<Tag>**, **List<String> → Set<Tag>**, hay **String[] → Tag[]**.

Điều kiện quan trọng là Spring cần biết **kiểu phần tử** của nguồn và đích. Thông tin generic của property hoặc **TypeDescriptor** cung cấp ngữ cảnh đó. Bài này giải thích cơ chế, cách đăng ký, sử dụng với **ConversionService**, tích hợp **DataBinder**, các trường hợp thất bại và ví dụ Java 17 chạy độc lập.

## 1. Ý tưởng: chuyển phần tử rồi chuyển cấu trúc

Giả sử ứng dụng có kiểu đích:

~~~java
public record Tag(String value) {}
~~~

và một converter:

~~~java
public final class StringToTagConverter implements Converter<String, Tag> {
    @Override
    public Tag convert(String source) {
        return new Tag(source.trim().toLowerCase(Locale.ROOT));
    }
}
~~~

Đây là hai đoạn minh họa; ví dụ chạy hoàn chỉnh ở phần 5 cung cấp đủ class và imports. Converter chỉ hiểu **String → Tag**. Nó không cần biết phần tử đang nằm trong array, List hay Set.

Nếu đầu vào là:

~~~text
[" Java ", "SPRING", "data-binding"]
~~~

và đích là **List<Tag>**, luồng logic:

~~~text
String[]  [" Java ", "SPRING", "data-binding"]
    |
    v
Array-to-Collection converter
    |
    +-- StringToTagConverter: " Java " -> Tag("java")
    +-- StringToTagConverter: "SPRING" -> Tag("spring")
    +-- StringToTagConverter: "data-binding" -> Tag("data-binding")
    |
    v
List<Tag>
~~~

Đây là cách kết hợp converter: một converter xử lý cấu trúc ngoài, converter giá trị xử lý từng phần tử. Converter cấu trúc do Spring cung cấp chịu trách nhiệm tạo container đích và lặp qua các phần tử; converter ứng dụng chỉ chuẩn hóa một chuỗi thành Tag.

| Kiểu nguồn | Kiểu đích | Converter cấu trúc | Converter giá trị được gọi |
| --- | --- | --- | --- |
| **String[]** | **List<Tag>** | Array-to-Collection | **String → Tag** cho từng chuỗi |
| **List<String>** | **Set<Tag>** | Collection-to-Collection | **String → Tag** cho từng phần tử |
| **String[]** | **Tag[]** | Array-to-Array | **String → Tag** cho từng phần tử |
| **List<Tag>** | **Tag[]** | Collection-to-Array | Không cần đổi kiểu phần tử |
| **Tag[]** | **List<Tag>** | Array-to-Collection | Không cần đổi kiểu phần tử |

Các trường hợp này cần container converter tương ứng được đăng ký và kiểu phần tử có thể xác định. Spring cung cấp converter chuẩn cho array/collection/map trong các ConversionService mặc định; với registry tối giản hoặc cặp kiểu đặc biệt, hãy kiểm tra đường chuyển đổi thực tế.

## 2. Các converter cấu trúc Spring cung cấp

**DefaultConversionService** đăng ký sẵn bộ converter phổ biến, gồm converter scalar và converter cho array, collection, map. Một số converter cấu trúc quan trọng:

- **ArrayToArrayConverter**: chuyển một mảng sang mảng khác; có thể chuyển từng phần tử nếu kiểu phần tử khác nhau.
- **ArrayToCollectionConverter**: chuyển mảng nguồn thành collection đích, dùng kiểu phần tử đích để chuyển từng item.
- **CollectionToArrayConverter**: chuyển collection nguồn sang mảng đích.
- **CollectionToCollectionConverter**: chuyển collection nguồn sang collection đích; có thể thay đổi kiểu container và kiểu phần tử.
- **MapToMapConverter**: chuyển map sang map; có thể chuyển key và value dựa trên descriptor tương ứng.
- Các converter scalar/container khác xử lý cặp kiểu phù hợp, ví dụ object thành collection hoặc collection thành object array.

Không nên phụ thuộc vào tên lớp triển khai nội bộ nếu chỉ cần API. Điều cần hiểu là **ConversionService** tìm đường chuyển đổi cấu trúc; mỗi phần tử sau đó có thể đi qua converter giá trị riêng. Nếu thiếu converter cho một phần tử, toàn bộ lần chuyển đổi container có thể thất bại dù converter cấu trúc tồn tại.

**Không bắt buộc viết GenericConverter chỉ vì dữ liệu là collection.** Với phép chuyển đổi cơ bản của phần tử, một **Converter<S, T>** có kiểu rõ ràng thường đơn giản và an toàn hơn. Chỉ cân nhắc **GenericConverter** khi logic thực sự phụ thuộc nhiều cặp kiểu, generic metadata, annotation hoặc context của field/property.

## 3. TypeDescriptor: cách Spring biết kiểu phần tử generic

Java generic bị **type erasure** ở runtime: từ một instance ArrayList đơn thuần, không thể luôn suy ra nó là **List<String>**, **List<Tag>** hay **List<Order>**. Muốn chuyển collection parameterized chính xác, Spring cần metadata bổ sung.

**org.springframework.core.convert.TypeDescriptor** mô tả một kiểu và ngữ cảnh nơi kiểu đó xuất hiện (field, method parameter, collection element, map key/value...). Nhờ đó **ConversionService** biết phần tử collection đích là gì.

Ví dụ mô tả **List<Tag>**:

~~~java
TypeDescriptor target = TypeDescriptor.collection(
        List.class,
        TypeDescriptor.valueOf(Tag.class));
~~~

Mô tả kiểu nguồn **String[]**:

~~~java
TypeDescriptor source = TypeDescriptor.valueOf(String[].class);
~~~

Khi có đủ hai mô tả, dùng overload chuyển đổi theo TypeDescriptor:

~~~java
Object result = conversionService.convert(
        sourceValue, sourceTypeDescriptor, targetTypeDescriptor);
~~~

Với ví dụ array sang List:

~~~java
List<Tag> tags = (List<Tag>) conversionService.convert(
        sourceArray,
        TypeDescriptor.valueOf(String[].class),
        TypeDescriptor.collection(List.class, TypeDescriptor.valueOf(Tag.class)));
~~~

Phương thức này nhận kiểu trả về là **Object**, vì vậy ví dụ ép kiểu về **List<Tag>**. Ứng dụng phải bảo đảm descriptor đích đúng với kiểu thực đang ép.

### Ba cách lấy TypeDescriptor

**Tạo tường minh** khi biết kiểu:

~~~java
TypeDescriptor tagsType = TypeDescriptor.collection(
        List.class, TypeDescriptor.valueOf(Tag.class));
~~~

**Lấy từ field Java có khai báo generic:**

~~~java
TypeDescriptor tagsField =
        new TypeDescriptor(RegistrationForm.class.getDeclaredField("tags"));
~~~

**Lấy từ tham số method/property** nếu cần mô tả context khai báo tương ứng. Nên giữ generic metadata từ Field/MethodParameter thay vì chỉ dùng raw List.class.

Một lưu ý: **TypeDescriptor.forObject(list)** không tự phục hồi generic **List<String>** đã bị type erasure nếu runtime chỉ cho biết object là ArrayList. Với collection có parameterized element type, dùng descriptor từ khai báo field hoặc tự tạo bằng **TypeDescriptor.collection(...)**.

### canConvert chưa bảo đảm mọi phần tử đều chuyển thành công

Khi chuyển array/collection/map, **canConvert(sourceType, targetType)** có thể trả true vì Spring tìm thấy converter cấu trúc phù hợp. Nhưng một phần tử cụ thể vẫn có thể thất bại khi gọi **convert(...)**. Ví dụ registry biết đường **String[] → List<Tag>**, nhưng converter **String → Tag** từ chối phần tử "bad value". Vì vậy phải xử lý ConversionException/ConversionFailedException từ lần chuyển đổi thật, không dùng riêng canConvert như xác nhận toàn bộ dữ liệu hợp lệ.

## 4. Đăng ký converter phần tử và phạm vi tái sử dụng

Một converter có thể được đăng ký vào registry như sau:

~~~java
DefaultConversionService service = new DefaultConversionService();
service.addConverter(new StringToTagConverter());
~~~

**DefaultConversionService** đã đăng ký converter mặc định cho các kiểu phổ biến và array/collection. Khi bổ sung **String → Tag**, các converter cấu trúc chuẩn có thể tái sử dụng nó.

Một ứng dụng Spring có thể quản lý ConversionService dưới dạng bean dùng chung hoặc dùng **FormattingConversionService** trong web. Cần đăng ký converter vào đúng registry mà đường xử lý thực tế sử dụng. Gọi **new DefaultConversionService()** trong test không làm converter tự xuất hiện trong MVC, binder khác hay Jackson.

Converter nên **stateless**, không giữ dữ liệu request trong field. ConversionService được thiết kế để dùng chung sau khi cấu hình ở startup; hoàn tất đăng ký trước khi có nhiều request. Tránh thay đổi registry trong lúc các luồng khác đang chuyển đổi dữ liệu.

**Khi nào cần converter riêng cho container?** Chỉ khi phép chuyển đổi cấu trúc khác quy tắc chuẩn, ví dụ phải gom nhiều phần tử thành một giá trị, chia một scalar theo delimiter riêng, xử lý container domain tùy biến, giữ metadata đặc biệt hoặc áp dụng quy tắc khác nhau tùy field. Với trường hợp thông thường, thêm converter scalar và để Spring làm phần container conversion sẽ ít code, dễ kiểm thử.

## 5. Ví dụ hoàn chỉnh Java 17: tái sử dụng converter cho array và collection

Chương trình sau dùng **Spring Framework 6.2.10**, JDK 17 trở lên và Maven; không cần Spring Boot hoặc web server. Nó đăng ký duy nhất **StringToTagConverter**, sau đó chuyển:

1. **String[] → List<Tag>**.
2. **List<String> → Set<Tag>**.
3. **String[] → Tag[]**.

Đầu vào được chuẩn hóa chữ thường và bỏ khoảng trắng; ví dụ **" java "** trở thành **Tag("java")**.

Cấu trúc dự án:

~~~text
converter-container-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ConverterContainerDemo.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>converter-container-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.10</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/ConverterContainerDemo.java**:

~~~java
package demo;

import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.converter.Converter;
import org.springframework.core.convert.support.DefaultConversionService;

public final class ConverterContainerDemo {

    public static void main(String[] args) {
        // Đăng ký converter cho một giá trị: String -> Tag.
        DefaultConversionService conversionService =
                new DefaultConversionService();
        conversionService.addConverter(new StringToTagConverter());

        // Case 1: String[] -> List<Tag>.
        String[] rawArray = {" Java ", "SPRING", "data-binding"};
        TypeDescriptor stringArray = TypeDescriptor.valueOf(String[].class);
        TypeDescriptor tagList = TypeDescriptor.collection(
                List.class, TypeDescriptor.valueOf(Tag.class));

        @SuppressWarnings("unchecked")
        List<Tag> tags = (List<Tag>) conversionService.convert(
                rawArray, stringArray, tagList);

        // Case 2: List<String> -> Set<Tag>.
        List<String> rawList = List.of(" MVC ", "JAVA", " spring ");
        TypeDescriptor stringList = TypeDescriptor.collection(
                List.class, TypeDescriptor.valueOf(String.class));
        TypeDescriptor tagSet = TypeDescriptor.collection(
                Set.class, TypeDescriptor.valueOf(Tag.class));

        @SuppressWarnings("unchecked")
        Set<Tag> tagSetResult = (Set<Tag>) conversionService.convert(
                rawList, stringList, tagSet);

        // Case 3: String[] -> Tag[].
        Tag[] tagArray = (Tag[]) conversionService.convert(
                new String[] {" HTTP ", "SPRING"},
                TypeDescriptor.valueOf(String[].class),
                TypeDescriptor.valueOf(Tag[].class));

        System.out.println("list = " + values(tags));
        System.out.println("set = " + values(tagSetResult));
        System.out.println("array = "
                + Arrays.stream(tagArray)
                        .map(Tag::value)
                        .collect(Collectors.joining(", ")));
        System.out.println("converterRegistered = "
                + conversionService.canConvert(String.class, Tag.class));
    }

    public record Tag(String value) {
    }

    public static final class StringToTagConverter
            implements Converter<String, Tag> {

        @Override
        public Tag convert(String source) {
            if (source == null) {
                return null;
            }

            String normalized = source.trim().toLowerCase(Locale.ROOT);
            if (normalized.isEmpty()) {
                throw new IllegalArgumentException("Tag must not be blank");
            }
            if (!normalized.matches("[a-z0-9-]+")) {
                throw new IllegalArgumentException(
                        "Tag contains unsupported characters: " + source);
            }
            return new Tag(normalized);
        }
    }

    private static String values(Iterable<Tag> tags) {
        StringBuilder result = new StringBuilder("[");
        boolean first = true;

        for (Tag tag : tags) {
            if (!first) {
                result.append(", ");
            }
            result.append(tag.value());
            first = false;
        }
        return result.append("]").toString();
    }
}
~~~

Tại thư mục chứa **pom.xml**, với JDK 17+ và Maven, chạy:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ConverterContainerDemo
~~~

**Các dòng do chính chương trình in ra**:

~~~text
list = [java, spring, data-binding]
set = [mvc, java, spring]
array = http, spring
converterRegistered = true
~~~

Set đích được tạo bởi cơ chế collection conversion mặc định, giữ thứ tự phần tử theo dữ liệu nguồn trong ví dụ. Chương trình không phụ thuộc thứ tự ngẫu nhiên của HashSet do ứng dụng tự tạo.

Phân tích:

- Converter chỉ được đăng ký một lần cho **String → Tag**. Không có class **StringArrayToTagListConverter** hoặc **StringListToTagSetConverter**.
- Khi chuyển **String[] → List<Tag>**, Spring tìm converter array-to-collection, đọc target element descriptor là Tag, rồi sử dụng converter String → Tag cho từng phần tử.
- Khi chuyển **List<String> → Set<Tag>**, converter collection-to-collection thực hiện cùng quy trình với container đích là Set.
- Khi chuyển **String[] → Tag[]**, converter array-to-array tái sử dụng converter phần tử cho array đích.
- **canConvert(String.class, Tag.class)** xác nhận converter scalar đã đăng ký; nó không thay thế việc thực sự gọi convert trên dữ liệu.

Nếu đổi một phần tử đầu vào thành **"java spring"**, converter ném **IllegalArgumentException**; ConversionService biểu diễn lỗi chuyển đổi tương ứng (thường là **ConversionFailedException** trong quá trình thực thi). Một container conversion có thể thất bại vì chỉ một phần tử lỗi; không nên bỏ qua exception rồi tiếp tục xử lý collection thiếu dữ liệu.

## 6. Chuyển collection generic trực tiếp: đừng bỏ quên TypeDescriptor

Một lỗi thường gặp là chỉ truyền **List.class** làm kiểu đích:

~~~java
conversionService.convert(input, List.class);
~~~

Cách này chỉ mô tả raw type List, không cho biết phần tử cần là Tag, String hay kiểu khác. Khi chuyển collection parameterized, cung cấp hai **TypeDescriptor**:

~~~java
List<Tag> result = (List<Tag>) conversionService.convert(
        input,
        TypeDescriptor.collection(
                List.class, TypeDescriptor.valueOf(String.class)),
        TypeDescriptor.collection(
                List.class, TypeDescriptor.valueOf(Tag.class)));
~~~

Đoạn minh họa giả định **input** thực sự là **List<String>** và đã đăng ký converter **String → Tag**. Cặp descriptor cho Spring biết kiểu nguồn là List<String> và kiểu đích là List<Tag>. Nếu generic source không khớp với dữ liệu runtime, vẫn có thể phát sinh lỗi; descriptor không biến dữ liệu thành đúng kiểu thay cho ứng dụng.

### Chuyển nested collection

Cơ chế có thể áp dụng cho container lồng nhau nếu converter cấu trúc và type descriptor cần thiết được hỗ trợ, ví dụ **List<List<Tag>>**. Khi nguồn là **String[][]** hoặc **List<List<String>>**, Spring phải biết container ngoài và kiểu phần tử bên trong. Raw **List.class** sẽ làm mất metadata cần thiết. Hãy lấy descriptor từ field generic được khai báo hoặc dựng descriptor lồng nhau rồi kiểm tra trên đúng cặp kiểu nguồn/đích.

Không nên suy ra mọi kiểu container tùy chỉnh hoặc mọi generic lồng nhau đều tự chuyển thành công. Collection interface phổ biến được Spring hỗ trợ; container đặc biệt có thể đòi hỏi converter bổ sung hoặc một implementation cụ thể.

## 7. Dùng converter phần tử trong DataBinder

Trong property binding, JavaBean có thể khai báo:

~~~java
public class SearchForm {
    private List<Tag> tags;

    public List<Tag> getTags() {
        return tags;
    }

    public void setTags(List<Tag> tags) {
        this.tags = tags;
    }
}
~~~

Đây là JavaBean minh họa để dùng với **DataBinder**. Khi nguồn là nhiều form parameters và đích property là **List<Tag>**, Spring có thể lấy kiểu phần tử từ generic declaration của property thông qua BeanWrapper/TypeDescriptor.

Đoạn cấu hình minh họa:

~~~java
SearchForm form = new SearchForm();

DefaultConversionService service = new DefaultConversionService();
service.addConverter(new StringToTagConverter());

DataBinder binder = new DataBinder(form, "searchForm");
binder.setConversionService(service);
binder.setAllowedFields("tags");
binder.bind(new MutablePropertyValues(Map.of(
        "tags", new String[] {" java ", "spring"})));

BindingResult result = binder.getBindingResult();
if (!result.hasErrors()) {
    System.out.println(form.getTags());
}
~~~

Đây là đoạn sử dụng **SearchForm** và **StringToTagConverter** ở phần trước, cần import **DataBinder**, **MutablePropertyValues**, **BindingResult** và **Map**. Với môi trường web, request parameters nhiều giá trị thường được biểu diễn thành String[]; với code thủ công, ta tạo mảng đó tường minh.

**setAllowedFields("tags")** giới hạn property mà client được phép bind. Converter phần tử chỉ chuyển kiểu, không kiểm tra người gửi có quyền chọn tag hay tag có tồn tại trong database.

Trong Spring MVC, converter tùy chỉnh cho phần tử có thể được đăng ký với **WebMvcConfigurer.addFormatters(...)** để MVC FormattingConversionService sử dụng. Sau đó binder của MVC dùng converter theo cấu hình framework. Tránh tạo service mới trong mỗi controller nếu ý định là cấu hình converter chung; đồng thời phân biệt đường **@ModelAttribute** với JSON body **@RequestBody**, vì Jackson deserialize JSON theo cơ chế riêng.

## 8. Khi nào dùng ConverterFactory hoặc GenericConverter?

**Converter<S, T>** phù hợp khi một cặp kiểu nguồn/đích rõ ràng, chẳng hạn **String → Tag**. Khi tái sử dụng cho collection/array, converter cấu trúc gọi nó cho từng phần tử.

**ConverterFactory<S, R>** phù hợp khi một kiểu nguồn chuyển thành một họ kiểu đích có chung gốc, ví dụ **String** sang nhiều kiểu enum. Đăng ký factory một lần và Spring chọn converter cụ thể theo kiểu đích.

**GenericConverter** hữu ích khi cần hỗ trợ nhiều cặp kiểu hoặc logic phụ thuộc **TypeDescriptor**. Ví dụ:

- Chuyển đổi có xét annotation trên field/property.
- Chuyển đổi yêu cầu generic metadata hoặc nested type.
- Converter tổng quát xử lý map key và value theo descriptor khác nhau.
- Quy tắc chuyển đổi khác nhau theo context nguồn/đích.

Không viết GenericConverter thay ArrayToCollectionConverter hoặc CollectionToCollectionConverter chuẩn chỉ vì đầu vào là container. Spring đã có converter cấu trúc. GenericConverter nên tập trung vào trường hợp thực sự cần metadata hoặc nhiều cặp kiểu, bởi API ít type-safe hơn Converter<S,T>.

Một GenericConverter/ConditionalGenericConverter có thể nhìn thấy annotation hoặc metadata của đích để quyết định có áp dụng hay không. Nếu logic phụ thuộc annotation ở field container, hãy kiểm thử xem context đó có sẵn trong descriptor phần tử theo cách bạn cần hay không; đừng mặc định annotation của container tự truyền sang từng element.

## 9. Những lỗi và giới hạn thường gặp

**Chỉ đăng ký converter scalar nhưng dùng ConversionService rỗng.** Converter String → Tag không tự tạo converter cấu trúc cho mọi array/collection. Dùng DefaultConversionService/DefaultFormattingConversionService hoặc chủ động đăng ký bộ converter mặc định phù hợp.

**Không cung cấp generic element type.** List.class không nói phần tử là gì. Dùng TypeDescriptor.collection(...) hoặc lấy descriptor từ field/method declaration.

**canConvert trả true nhưng convert vẫn thất bại.** Với container, Spring có thể biết converter cấu trúc tồn tại nhưng từng item không chuyển được. Bao quanh convert bằng xử lý lỗi thích hợp và trả thông báo cụ thể theo phần tử khi cần.

**Converter không xử lý blank theo đúng hợp đồng.** Phần tử null có thể được xử lý theo null semantics của ConversionService; chuỗi rỗng/whitespace là một giá trị và converter cần quyết định chuẩn hóa hoặc từ chối. Không biến blank thành Tag hợp lệ nếu nghiệp vụ không cho phép.

**Converter phụ thuộc database hoặc user state.** Converter có thể được dùng cho nhiều request/luồng; truy vấn database hoặc phân quyền trong convert làm parse kiểu khó dự đoán và tốn kém. Giữ converter thuần túy; kiểm tra tồn tại, trạng thái và quyền ở service/domain sau khi chuyển đổi.

**Bỏ qua phần tử lỗi.** Nếu một phần tử sai định dạng, không âm thầm lọc bỏ rồi trả collection thiếu phần tử. Xác định rõ chính sách all-or-nothing hoặc xây cơ chế thu thập lỗi theo từng index ở tầng chuyên biệt.

**Đăng ký converter trùng hoặc xung đột.** Nhiều converter cùng cặp kiểu khiến lựa chọn khó hiểu hoặc phụ thuộc registry. Đăng ký quy tắc rõ ràng và test đúng cặp kiểu.

**Nhầm ArrayToCollection với chuyển scalar thành list.** Khả năng chuyển **String[] → List<Tag>** không khẳng định **String → List<Tag>** cũng được hỗ trợ. Nếu input chỉ là một chuỗi và cần tách delimiter, hãy định nghĩa rõ cú pháp và viết converter phù hợp.

**Dùng @RequestBody để kiểm tra property binding.** JSON converter/deserializer đọc body theo cơ chế riêng. Dùng DataBinder hoặc form @ModelAttribute nếu mục tiêu là xác minh array/collection element conversion qua property binding.

## 10. Kiểm thử và lựa chọn cách triển khai

| Ca kiểm thử | Kiểu nguồn → đích | Điều cần xác nhận |
| --- | --- | --- |
| Một giá trị | **String → Tag** | Converter trim, normalize và tạo Tag đúng |
| Mảng → List | **String[] → List<Tag>** | Mỗi phần tử chuyển đúng, giữ thứ tự |
| List → Set | **List<String> → Set<Tag>** | Element converter tái sử dụng, container đích đúng |
| Mảng → mảng | **String[] → Tag[]** | Kiểu phần tử đích được áp dụng |
| Giá trị lỗi ở giữa | **String[] → List<Tag>** có một item sai | Lời gọi convert báo lỗi, không giả vờ thành công toàn bộ |
| TypeDescriptor sai | Descriptor raw hoặc element không khớp | Tránh mất generic metadata |
| DataBinder | Form List<Tag> nhận String[] | BindingResult và target đúng |
| Multi-thread | Nhiều request dùng chung service | Converter stateless, không rò trạng thái |
| MVC registration | Converter đăng ký qua addFormatters | Endpoint form dùng đúng registry |
| JSON riêng | @RequestBody có collection | Xác minh deserialization path riêng |

Trong test đơn vị, kiểm tra **size**, **thứ tự**, **giá trị phần tử** và exception khi có phần tử lỗi. Với Set, thêm test duplicate để xác nhận semantics của container; Set có thể loại phần tử trùng dựa trên equals/hashCode của kiểu phần tử. Với Map, test riêng key và value descriptor vì lỗi ở một trong hai phía đều có thể làm toàn bộ conversion thất bại.

### Chọn giải pháp

- **Chỉ đổi kiểu phần tử, container theo quy tắc chuẩn:** viết một Converter<S,T>, đăng ký vào DefaultConversionService và để Spring xử lý array/collection.
- **Chuyển parameterized collection bằng code trực tiếp:** cung cấp TypeDescriptor cho nguồn và đích để giữ generic metadata.
- **Cần parse/print phụ thuộc locale:** cân nhắc Formatter<T>.
- **Cần một họ kiểu đích từ chung một nguồn:** cân nhắc ConverterFactory.
- **Cần metadata/annotation hoặc nhiều cặp kiểu:** cân nhắc GenericConverter/ConditionalGenericConverter.
- **Cần validate nội dung, database hoặc quyền:** thực hiện ở Validator/service/domain, không nhét side effect vào element converter.

Nguyên tắc cần nhớ là **tách chuyển đổi phần tử khỏi chuyển đổi cấu trúc**. Converter giá trị làm một việc nhỏ, có kiểu rõ ràng; ConversionService và TypeDescriptor phối hợp để tái sử dụng logic đó trên từng phần tử của array/collection khi có đường chuyển đổi chuẩn.

## Tài liệu chính thức

- [Spring Framework — Type Conversion: Converter, ConversionService và tái sử dụng cho array/collection](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Framework 6.2.10 API — ConversionService](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/core/convert/ConversionService.html)
- [Spring Framework 6.2.10 API — TypeDescriptor](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/core/convert/TypeDescriptor.html)
- [Spring Framework 6.2.10 API — DefaultConversionService](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/core/convert/support/DefaultConversionService.html)
- [Spring Framework — Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html)
- [Spring MVC — Conversion and Formatting](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html)
