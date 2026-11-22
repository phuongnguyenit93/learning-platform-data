# Chuyển đổi mảng, Collection và Map bằng Spring ConversionService

## 1. Vì sao chuyển đổi container cần metadata?

Spring ConversionService không chỉ chuyển một giá trị đơn như `String → Integer`. Nó còn có thể chuyển đổi dữ liệu dạng container:

- Mảng sang Collection: `String[] → List<Integer>`.
- Collection sang mảng: `List<String> → Integer[]`.
- Collection sang Collection: `List<String> → Set<Long>`.
- Map sang Map: `Map<String, String> → Map<Integer, Boolean>`.
- Chuỗi dạng danh sách sang Collection, hoặc Collection sang chuỗi, khi có converter phù hợp.

Chuyển đổi container có hai lớp công việc:

1. Chuyển **cấu trúc bên ngoài**: array, list, set hay map.
2. Chuyển **từng phần tử**: element của array/collection; key và value của map.

Ví dụ `String[] → List<Integer>` cần biết target là List có phần tử Integer. Spring có thể tạo collection đích phù hợp và dùng ConversionService để chuyển từng chuỗi sang Integer. Tương tự, khi đổi Map, Spring có thể chuyển riêng key và value theo metadata generic.

Điểm quan trọng là Java reflection ở runtime thường chỉ cho biết `List.class` nếu ta dùng `Class<?>`; nó không đủ để phân biệt `List<String>` và `List<Integer>`. Spring dùng **`TypeDescriptor`** để mang theo generic element type, map key/value type và annotation từ vị trí khai báo.

## 2. Những kiểu container và hướng chuyển đổi

| Nguồn | Đích | Việc Spring cần làm |
| --- | --- | --- |
| `String[]` | `List<Integer>` | Tạo collection, chuyển từng String sang Integer |
| `List<String>` | `Integer[]` | Tạo array đích, chuyển từng phần tử sang Integer |
| `List<String>` | `Set<Long>` | Tạo Set, chuyển từng phần tử sang Long; Set loại bỏ phần tử trùng theo quy tắc equals/hashCode |
| `Set<String>` | `List<UUID>` | Tạo List và chuyển từng String sang UUID |
| `Map<String,String>` | `Map<Integer,Boolean>` | Chuyển mỗi key String sang Integer và mỗi value String sang Boolean |
| `String` | `List<Integer>` | Có thể dùng converter chuỗi → collection; cách tách chuỗi và phần tử phụ thuộc converter đăng ký |
| `List<Integer>` | `String` | Cần converter collection → string tương ứng và quy tắc biểu diễn |

Các chuyển đổi container không phải phép cast. `(List<Integer>) someList` chỉ ép kiểu ở compile/runtime; nó không parse từng chuỗi thành số. ConversionService thực sự dựng dữ liệu đích và chuyển các phần tử.

### Những converter nền tảng của Spring

`DefaultConversionService` đăng ký nhiều converter tích hợp cho các cặp container thường gặp, trong đó có array-to-collection, collection-to-array, collection-to-collection và map-to-map, bên cạnh các converter cho phần tử phổ biến. Các converter này tận dụng ConversionService để chuyển đổi phần tử lồng bên trong.

Không nên giả định rằng mọi cặp container đều được hỗ trợ trong mọi trường hợp. Khả năng còn tùy:
- Cặp kiểu nguồn/đích.
- Generic metadata có sẵn hay không.
- Các converter cho kiểu phần tử, map key và map value.
- Converter tùy biến đã đăng ký.
- Khả năng tạo instance cho kiểu collection/map đích.

## 3. Class và TypeDescriptor: khác biệt quyết định

### Dùng Class khi kiểu đích không có generic cần phân biệt

Overload đơn giản:

```java
List<?> values = conversionService.convert(
    new String[]{"10", "20"}, List.class
);
```

Ở đây target là `List.class`. Spring biết cần một List, nhưng không có đủ thông tin generic để khẳng định phần tử phải là `Integer`. Đừng ép kết quả thành `List<Integer>` chỉ dựa vào cast: generic type đã bị xóa ở runtime và dữ liệu phần tử có thể không mang kiểu bạn mong muốn.

### Dùng TypeDescriptor để nói rõ kiểu phần tử

`TypeDescriptor` mô tả một kiểu cùng metadata tại vị trí khai báo. Có thể lấy descriptor từ field:

```java
Field field = Form.class.getDeclaredField("numbers");
TypeDescriptor targetDescriptor =
    new TypeDescriptor(new Property(field));
```

Nếu field được khai báo `List<Integer> numbers`, descriptor giữ thông tin generic Integer. Spring có thể dùng metadata đó để tìm converter chuyển từng phần tử.

Một số factory method hữu ích:

```java
TypeDescriptor.valueOf(String[].class);
TypeDescriptor.collection(
    List.class, TypeDescriptor.valueOf(Integer.class)
);
TypeDescriptor.map(
    Map.class,
    TypeDescriptor.valueOf(Integer.class),
    TypeDescriptor.valueOf(Boolean.class)
);
```

Cách này thuận tiện khi kiểu generic được biết rõ trong code. Với annotation hoặc nested generic phức tạp, lấy descriptor từ field, getter, constructor parameter hoặc method parameter sẽ giữ được metadata thực tế đầy đủ hơn.

### Overload convert dùng TypeDescriptor

```java
Object result = conversionService.convert(
    source,
    sourceDescriptor,
    targetDescriptor
);
```

Spring tra cứu converter theo **descriptor nguồn và đích**. Đối với container, descriptor đích cung cấp element type hoặc key/value type. Khi converter nền tảng duyệt từng phần tử, nó có thể yêu cầu ConversionService chuyển phần tử với descriptor tương ứng.

Nếu không cần metadata đặc biệt, dùng `convert(source, Target.class)` là đủ. Khi làm việc với generic collection/map, nên chủ động dùng TypeDescriptor thay vì kỳ vọng Class tự mang thông tin generic.

## 4. Mảng và Collection: chuyển từng phần tử

### Array → Collection

Ví dụ:

```java
String[] source = {"10", "20", "30"};
List<Integer> target = ...;
```

Quá trình có thể hình dung:

1. Spring nhận diện source là array và target là Collection.
2. Xác định kiểu phần tử đích từ descriptor, ví dụ Integer.
3. Tạo collection phù hợp với kiểu đích (ví dụ ArrayList cho List).
4. Duyệt các phần tử nguồn.
5. Gọi conversion cho từng phần tử từ String sang Integer.
6. Trả collection chứa các phần tử đã chuyển đổi.

Kích thước collection bằng số phần tử nguồn nếu tất cả đều chuyển đổi thành công. Nếu một phần tử lỗi, toàn lần convert có thể thất bại; không nên giả định Spring trả collection một phần.

### Collection → Array

Ví dụ `List<String> → Integer[]` cần:

1. Đọc element descriptor của collection nguồn khi có.
2. Xác định component type của array đích là Integer.
3. Tạo array đúng độ dài.
4. Chuyển từng phần tử rồi đặt vào đúng index.

Array có component type cố định. Nếu một phần tử không chuyển được, conversion thất bại; Java không tạo một array "trộn kiểu".

### Collection → Collection

Ví dụ `List<String> → Set<Long>`:

- Tạo collection đích dựa trên kiểu target.
- Chuyển từng phần tử sang Long.
- Thêm từng phần tử vào collection đích.

Nếu target là Set, các phần tử trùng nhau có thể được gộp theo quy tắc equality của kiểu phần tử; thứ tự chỉ được bảo đảm bởi implementation cụ thể (LinkedHashSet giữ thứ tự chèn, HashSet không cam kết thứ tự). Với List, các phần tử được giữ theo thứ tự duyệt nguồn trong trường hợp converter collection phù hợp.

Không nên dùng collection conversion để kiểm soát thứ tự hoặc tính duy nhất nghiệp vụ nếu kiểu đích không bảo đảm những đặc tính đó.

## 5. Map → Map: chuyển key và value độc lập

Giả sử:

```java
Map<String, String> source = Map.of(
    "1", "true",
    "2", "false"
);
```

Target mong muốn `Map<Integer, Boolean>`. Có hai luồng chuyển đổi:

- Key: `String → Integer`.
- Value: `String → Boolean`.

Spring cần biết cả hai generic argument trên descriptor đích. Vì vậy, với Map cũng không nên chỉ truyền `Map.class` nếu muốn chuyển key/value sang kiểu khác.

Luồng tổng quát:

```text
Map<String, String>
       |
       v
Map-to-Map converter
       |
       +--> convert each key:   String -> Integer
       |
       +--> convert each value: String -> Boolean
       |
       v
Map<Integer, Boolean>
```

Những tình huống có thể lỗi:

- Key `"x"` không parse được thành Integer.
- Value `"perhaps"` không chuyển được thành Boolean theo converter đang dùng.
- Hai key nguồn khác nhau khi chuyển có thể trở thành cùng một key đích; map đích chỉ giữ một entry theo quy tắc put của Map.
- Kiểu Map đích không thể tạo instance hoặc không phù hợp với cấu trúc được converter hỗ trợ.

**Không giả định key collision sẽ tự báo lỗi.** Nếu cần phát hiện hai key khác nhau cùng chuyển thành một key đích, hãy kiểm tra riêng trong logic nghiệp vụ hoặc viết converter tùy biến phù hợp. Tương tự, Map conversion không tự xác thực rằng key tồn tại trong hệ thống.

## 6. String sang Collection: delimiter và cách tách

Spring có converter tích hợp cho một số trường hợp chuỗi thành array/collection. Ví dụ dữ liệu:

```text
10,20,30
```

có thể chuyển thành collection số với converter phù hợp, do cơ chế tách chuỗi và element conversion.

Tuy nhiên, đừng giả định mọi chuỗi đều được tách theo dấu phẩy trong mọi converter tùy biến. Hãy xác nhận converter nào được đăng ký, định dạng delimiter, cách xử lý khoảng trắng, phần tử rỗng và dấu phẩy nằm trong giá trị có quote.

Nếu định dạng input thuộc một giao thức cụ thể, nên định nghĩa converter rõ ràng. Ví dụ CSV có quoting/escaping thực sự phức tạp hơn `String.split(",")`; không nên tự viết một bộ parse CSV đơn giản rồi dùng trong production.

### Ví dụ converter chuỗi tự định nghĩa

```java
public final class CsvToIntegerList
        implements Converter<String, List<Integer>> {

    @Override
    public List<Integer> convert(String source) {
        if (source == null || source.isBlank()) {
            return List.of();
        }
        return Arrays.stream(source.split(","))
            .map(String::trim)
            .map(Integer::valueOf)
            .toList();
    }
}
```

Đây là snippet minh họa cần import `Arrays` và `List`. Nó định nghĩa quy tắc rất đơn giản: tách bằng dấu phẩy, trim và parse Integer. `Integer.valueOf` có thể ném `NumberFormatException`; khi converter chạy qua ConversionService, lỗi thường được bọc thành `ConversionFailedException`. Chỉ sử dụng cách này nếu format đầu vào thực sự không có quoting/escaping phức tạp.

## 7. Ví dụ Java 17 chạy được: array, collection và map

Chương trình sau dùng Spring Framework 6.1.14 và `DefaultConversionService`. Nó chuyển ba cấu trúc bằng `TypeDescriptor` đọc từ field generic, để chứng minh phần tử, key và value đều được chuyển theo kiểu đích.

Cấu trúc:

```text
container-conversion-demo/
├── pom.xml
└── src/main/java/demo/ContainerConversionDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>container-conversion-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <maven.compiler.parameters>true</maven.compiler.parameters>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.14</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/ContainerConversionDemo.java`:

```java
package demo;

import java.lang.reflect.Field;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.beans.Property;
import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.support.DefaultConversionService;

public final class ContainerConversionDemo {

    public static final class Targets {
        private List<Integer> numbers;
        private Set<Long> uniqueNumbers;
        private Map<Integer, Boolean> flags;

        public List<Integer> getNumbers() {
            return numbers;
        }

        public Set<Long> getUniqueNumbers() {
            return uniqueNumbers;
        }

        public Map<Integer, Boolean> getFlags() {
            return flags;
        }
    }

    private static TypeDescriptor fieldType(String name)
            throws NoSuchFieldException {
        Field field = Targets.class.getDeclaredField(name);
        return new TypeDescriptor(new Property(field));
    }

    public static void main(String[] args) throws Exception {
        ConversionService service =
            new DefaultConversionService();

        String[] rawNumbers = {"10", "20", "30"};
        List<Integer> numbers = (List<Integer>) service.convert(
            rawNumbers,
            TypeDescriptor.valueOf(String[].class),
            fieldType("numbers")
        );

        List<String> rawUnique = List.of("2", "2", "5");
        Set<Long> unique = (Set<Long>) service.convert(
            rawUnique,
            TypeDescriptor.collection(
                List.class, TypeDescriptor.valueOf(String.class)
            ),
            fieldType("uniqueNumbers")
        );

        Map<String, String> rawFlags = Map.of(
            "1", "true",
            "2", "false"
        );
        Map<Integer, Boolean> flags =
            (Map<Integer, Boolean>) service.convert(
                rawFlags,
                TypeDescriptor.map(
                    Map.class,
                    TypeDescriptor.valueOf(String.class),
                    TypeDescriptor.valueOf(String.class)
                ),
                fieldType("flags")
            );

        System.out.println("arrayToList=" + numbers);
        System.out.println("listToSet=" + unique);
        System.out.println("mapToMap=" + flags);
    }
}
```

Chạy từ thư mục có `pom.xml`, với JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ContainerConversionDemo
```

Các dòng chương trình in ra:

```text
arrayToList=[10, 20, 30]
listToSet=[2, 5]
mapToMap={1=true, 2=false}
```

Giải thích:

1. `String[]` được chuyển sang `List<Integer>`. Target descriptor lấy từ field `numbers` nên Spring biết element type là Integer; từng chuỗi được parse.
2. `List<String>` được chuyển thành `Set<Long>`. Descriptor target của `uniqueNumbers` chứa Long; hai chuỗi `"2"` trở thành cùng giá trị Long 2 và Set chỉ giữ một phần tử.
3. `Map<String,String>` chuyển thành `Map<Integer,Boolean>`. Source descriptor có key/value String; target field descriptor có key Integer và value Boolean. Spring chuyển cả hai phần.
4. Thứ tự Map trong output có thể phụ thuộc implementation được tạo. Với converter mặc định và ví dụ này thường là Map giữ thứ tự duyệt; không nên xem thứ tự là một cam kết chung nếu target type không quy định.
5. Ví dụ cho thấy metadata generic đến từ field; nếu chỉ dùng `Map.class` hoặc `List.class`, việc chuyển phần tử theo kiểu đích có thể không được xác định như mong muốn.

Lưu ý: đoạn code ép kiểu kết quả từ overload TypeDescriptor sang generic container để gán vào biến Java. Đây là cast có kiểm soát theo target descriptor đã truyền; không phải cách thay thế generic metadata. Trong ứng dụng thực, nếu không thể đảm bảo descriptor đúng, cần xử lý/kiểm tra kiểu kết quả thay vì cast mù quáng.

## 8. Lỗi khi chuyển một phần tử trong container

Một container có thể có nhiều phần tử hợp lệ nhưng chỉ một phần tử sai:

```java
String[] input = {"10", "20", "not-a-number"};
```

Khi chuyển sang `List<Integer>`, phần tử thứ ba không parse được. Toàn bộ conversion có thể thất bại và ConversionService ném `ConversionException`; một converter container thông thường không trả lại collection nửa thành công rồi lặng lẽ bỏ phần tử lỗi.

Có thể bắt lỗi ở ranh giới chuyển đổi:

```java
try {
    List<Integer> result =
        service.convert(input, targetType);
} catch (ConversionException ex) {
    // Xử lý đầu vào không thể chuyển đổi.
}
```

Đoạn này minh họa cách xử lý; `targetType` và `service` cần được khai báo phù hợp. Khi cần báo chính xác vị trí phần tử lỗi, exception từ converter lồng có thể không cung cấp index theo định dạng mà API public mong muốn. Trong trường hợp đó, viết logic parse có kiểm soát từng phần tử hoặc custom converter để bổ sung thông tin index, ví dụ `items[2]`.

### Không tự bỏ phần tử sai

Một thiết kế như:

```java
for (String value : source) {
    try {
        result.add(Integer.valueOf(value));
    } catch (NumberFormatException ignored) {
        // bỏ qua
    }
}
```

có thể biến dữ liệu sai thành dữ liệu thiếu mà caller không biết. Chỉ dùng skip policy nếu nghiệp vụ cho phép rõ ràng và output có thông tin số phần tử bị loại; còn không, hãy fail conversion để tránh xử lý dữ liệu không đầy đủ.

### Giới hạn kích thước và tài nguyên

Input collection/map do client gửi có thể rất lớn. ConversionService thực hiện công việc trên những phần tử được cung cấp; không nên dựa vào conversion layer làm giới hạn tài nguyên. Tầng nhận request cần giới hạn:
- Kích thước body/query parameter.
- Số lượng phần tử.
- Độ dài từng chuỗi.
- Độ sâu nested data và chỉ số collection.
- Số lượng entry Map.

Nếu không, việc chuyển một mảng rất lớn sang collection có thể tiêu thụ CPU/bộ nhớ đáng kể.

## 9. Converter mặc định và converter tùy biến cho container

Trước khi tự viết converter, hãy thử `DefaultConversionService` với đúng source/target descriptors. Converter tích hợp đã xử lý nhiều trường hợp element conversion, container construction và generic metadata.

Khi cần logic riêng:

### Chuyển từng phần tử qua ConversionService

Một custom container converter không nên tự parse mọi kiểu bằng if/else. Có thể nhận ConversionService hoặc sử dụng cơ chế delegate phù hợp để chuyển từng phần tử. Cần bảo đảm converter không tạo vòng lặp tự gọi chính nó cho cùng descriptor.

### GenericConverter

`GenericConverter` phù hợp khi cặp kiểu đích có generic khác nhau và cần truy cập `TypeDescriptor`. Ví dụ converter array-to-specialized-collection cần biết target element descriptor để convert từng phần tử.

### ConditionalGenericConverter

Dùng khi cần chọn converter theo annotation hoặc metadata của container/element. Ví dụ chỉ map một `String[]` thành collection enum khi target field có annotation riêng. Điều kiện matching cần đủ cụ thể để không chiếm đường chuyển đổi thông thường.

### Không ghi đè converter mặc định tùy tiện

Đăng ký custom converter cho cặp kiểu rộng như `Object → Collection` có thể ảnh hưởng rất nhiều luồng chuyển đổi. Hãy dùng source/target pair cụ thể và test các trường hợp tương tác với converter mặc định.

## 10. Tích hợp với DataBinder và Spring MVC

`DataBinder` và `WebDataBinder` dùng ConversionService để chuyển dữ liệu property/form sang kiểu Java. Ví dụ form có field `List<Integer> itemIds`, binder có thể cần chuyển giá trị nguồn từ request sang collection phần tử Integer nếu cấu trúc dữ liệu và resolver/binding path phù hợp.

Trong Spring MVC, có thể đăng ký converter ở cấu hình MVC:

```java
@Configuration
class WebConfig implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToItemCodeConverter());
    }
}
```

Đoạn minh họa cần một converter `StringToItemCodeConverter` triển khai phù hợp và dependency Spring MVC. Sau đó, MVC có thể sử dụng nó trong binding/conversion tại các điểm hỗ trợ.

Cần phân biệt:
- `@ModelAttribute` sử dụng DataBinder/WebDataBinder và property/constructor binding theo ngữ cảnh.
- `@RequestBody` JSON thường được đọc qua HttpMessageConverter (ví dụ Jackson), không nhất thiết qua cùng đường ConversionService của DataBinder.
- Jackson có cơ chế deserialization collection/map riêng. Đừng suy luận rằng custom Spring Converter tự động thay đổi cách Jackson đọc mọi JSON array/object.
- Sau khi container đã được dựng, validation có thể kiểm tra từng phần tử hoặc quan hệ giữa các phần tử bằng Bean Validation/Spring Validator tùy cấu hình.

## 11. Null, empty và phần tử trùng

Ba trạng thái này có ý nghĩa khác nhau:

| Trạng thái | Ý nghĩa |
| --- | --- |
| Container null | Không có container; cách chuyển phụ thuộc converter/null semantics và target nullable |
| Container rỗng | Có container hợp lệ với 0 phần tử |
| Container có phần tử null | Có vị trí phần tử nhưng giá trị không được cung cấp; converter element có thể xử lý khác nhau |

Đừng gộp null thành empty nếu nghiệp vụ phân biệt "chưa cung cấp" và "đã cung cấp danh sách rỗng". Với Map, key null và value null cũng phụ thuộc kiểu Map đích và converter.

Phần tử trùng:
- List giữ phần tử lặp.
- Set loại giá trị trùng dựa trên `equals/hashCode`.
- Map không giữ nhiều entry cùng key sau khi key chuyển đổi; lần put sau có thể ghi đè giá trị trước tùy implementation.
- Nếu cần phát hiện trùng trước khi dữ liệu bị gộp, phải thực hiện kiểm tra riêng hoặc sử dụng converter có kiểm soát collisions.

## 12. Các lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `List<String>` được tạo nhưng phần tử không phải Integer | Chỉ truyền `List.class`, thiếu generic target descriptor | Lấy `TypeDescriptor` từ field/parameter hoặc tạo collection descriptor có element type |
| `canConvert` true nhưng một phần tử lỗi | Cặp container được hỗ trợ nhưng giá trị cụ thể không hợp lệ | Bắt `ConversionException`, kiểm tra cause và phần tử gây lỗi |
| `Map` chuyển key nhưng value vẫn String | Descriptor target thiếu key/value types hoặc bị mất generic | Dùng descriptor Map cụ thể và test cả hai phía |
| `Set` bị mất phần tử trùng | Đây là semantics của Set | Chọn List nếu cần giữ duplicates hoặc validate duplicates trước chuyển đổi |
| Map đích bị ghi đè entry | Hai key nguồn chuyển về cùng key đích | Phát hiện collisions trước/sau conversion theo nghiệp vụ |
| Không tạo được Collection đích | Kiểu đích/interface/implementation không được hỗ trợ hoặc không thể khởi tạo | Chọn kiểu đích cụ thể phù hợp hoặc viết converter riêng |
| Chuỗi CSV tách sai | Giả định delimiter/escaping không đúng | Định nghĩa format và parser rõ ràng |
| Custom converter không chạy | Đăng ký nhầm ConversionService | Kiểm tra registry mà MVC/DataBinder thực sự sử dụng |
| JSON array không dùng Spring Converter mong đợi | Body được deserialize bởi Jackson | Cấu hình Jackson module/deserializer hoặc xử lý tại HTTP converter |
| Input container quá lớn | Không có giới hạn tài nguyên ở tầng nhận request | Đặt giới hạn kích thước, phần tử và độ sâu trước conversion |

## 13. Quy trình gỡ lỗi conversion container

1. Ghi rõ **source descriptor** và **target descriptor**, gồm element type hoặc map key/value.
2. Xác nhận converter container phù hợp có trong registry.
3. Kiểm tra converter phần tử: `String → Integer`, `String → UUID`, `String → Boolean`...
4. Thử một container nhỏ có toàn phần tử hợp lệ.
5. Thử dữ liệu có đúng một phần tử sai để xác nhận exception được propagate.
6. Test phần tử trùng, null, empty, map key collision và nested paths nếu nghiệp vụ có liên quan.
7. Nếu chỉ lỗi trong MVC, xác minh dữ liệu đi qua `@ModelAttribute`, request parameter hay JSON deserializer.
8. Kiểm tra giới hạn kích thước input để tránh vấn đề CPU/memory với container lớn.

## 14. Câu hỏi tự kiểm tra

1. Vì sao `String[] → List<Integer>` cần target element metadata?
2. `TypeDescriptor` cung cấp thông tin gì mà `List.class` không có?
3. Trong `Map<String,String> → Map<Integer,Boolean>`, Spring cần thực hiện bao nhiêu hướng element conversion?
4. Vì sao `canConvert` có thể trả true nhưng `convert` vẫn thất bại khi một phần tử không hợp lệ?
5. Khác biệt về kết quả khi target là List và Set là gì?
6. Nếu hai key nguồn chuyển thành một key đích, điều gì có thể xảy ra và cần phát hiện ra sao?
7. Vì sao không nên lặng lẽ bỏ qua phần tử parse lỗi?
8. Khi nào nên viết `GenericConverter` thay vì `Converter<S,T>`?
9. `@RequestBody` JSON array có nhất thiết đi qua Spring DataBinder ConversionService không?
10. Cần giới hạn những gì khi nhận collection/map lớn từ bên ngoài?

**Ghi nhớ:** Spring chuyển đổi container bằng cách kết hợp converter cho cấu trúc ngoài với converter cho từng phần tử. Với Collection, cần biết element type; với Map cần biết key type và value type. Dùng `TypeDescriptor` để giữ generic metadata, không dựa vào `List.class`/`Map.class` khi đích có kiểu phần tử cụ thể. `canConvert` chỉ kiểm tra khả năng theo descriptor; dữ liệu từng phần tử vẫn có thể khiến `convert` thất bại.

## Tài liệu tham khảo

- Spring Framework — Type Conversion: https://docs.spring.io/spring-framework/reference/core/validation/convert.html
- Spring Framework 6.1.14 — TypeDescriptor Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/core/convert/TypeDescriptor.html
- Spring Framework 6.1.14 — ConversionService Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/core/convert/ConversionService.html
- Spring Framework 6.1.14 — GenericConversionService Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/core/convert/support/GenericConversionService.html
- Spring Framework 6.1.14 — DefaultConversionService Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/core/convert/support/DefaultConversionService.html
- Spring Framework — Data Binding: https://docs.spring.io/spring-framework/reference/core/validation/beans-beans.html
