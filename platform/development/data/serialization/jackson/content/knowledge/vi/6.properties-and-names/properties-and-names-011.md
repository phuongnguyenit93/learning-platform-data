# Xác định ưu tiên khi annotation xuất hiện ở nhiều thành phần

Trong Jackson Databind, một thuộc tính JSON có thể được mô tả bởi nhiều thành phần của cùng một class Java: field, getter, setter hoặc tham số constructor/factory được dùng để tạo object. Những thành phần này có thể cùng đại diện cho một logical property. Nếu annotation của Jackson xuất hiện ở nhiều nơi, Jackson phải kết hợp metadata để quyết định cách đọc và ghi thuộc tính đó.

Không có một câu trả lời duy nhất kiểu “field luôn thắng” hoặc “getter luôn thắng”. Thứ tự ưu tiên phụ thuộc vào hướng xử lý:

- Khi **serialize Java thành JSON**, getter thường được ưu tiên trước field.
- Khi **deserialize JSON thành Java**, tham số creator (constructor/factory) được ưu tiên trước setter, sau đó đến field; getter có thể là phương án sau cùng trong những cấu hình và loại thuộc tính phù hợp.

Thứ tự này giúp Jackson chọn thành phần chính cho từng hướng xử lý. Annotation của các thành phần còn lại vẫn có thể được hợp nhất làm metadata bổ sung. Vì vậy, cần phân biệt việc chọn accessor chính với quy tắc riêng của từng annotation.

## 1. Một thuộc tính Java có thể có nhiều thành phần

Xét class sau:

```java
public class User {
    private String name;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
```

Jackson có thể nhận diện `name` từ ba thành phần:

| Thành phần | Vai trò thường gặp |
|---|---|
| `name` field | Nơi lưu giá trị trong object |
| `getName()` | Cung cấp giá trị khi serialize |
| `setName(...)` | Nhận giá trị khi deserialize |

Jackson không nhất thiết xem ba thành phần trên là ba thuộc tính JSON riêng biệt. Qua quá trình introspection, chúng thường được gom thành một thuộc tính logic tên `name`.

Một thuộc tính có thể có thêm tham số constructor:

```java
public class User {
    private final String name;

    @JsonCreator
    public User(@JsonProperty("name") String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
```

Trong trường hợp này, constructor parameter là một creator property dùng để tạo object khi deserialize. Getter vẫn có thể cung cấp giá trị cho serialization. Jackson phải xem các thành phần này trong cùng ngữ cảnh thuộc tính để xây dựng metadata phù hợp.

## 2. Jackson tìm và gom logical property như thế nào?

Trước khi quyết định annotation nào có ưu tiên, Jackson cần tìm ra những thành phần nào được xem là thuộc tính có thể đọc hoặc ghi.

Quá trình khái quát gồm các bước:

1. **Introspection:** xem xét field, getter, setter và constructor/factory creator trong kiểu Java.
2. **Visibility:** xác định thành phần nào được nhận diện theo quy tắc truy cập mặc định, `@JsonAutoDetect` và cấu hình mapper.
3. **Property naming:** xác định tên logic từ quy ước Java Bean hoặc tên tường minh trong `@JsonProperty`.
4. **Grouping:** gom những thành phần cùng đại diện cho một thuộc tính logic.
5. **Annotation merging:** kết hợp annotation từ các thành phần theo hướng serialize hoặc deserialize.
6. **Property construction:** tạo metadata và chọn accessor/mutator phù hợp để thực hiện thao tác.

Do đó, một annotation chỉ có thể tham gia vào quá trình xử lý nếu thành phần chứa nó được Jackson nhận diện. `@JsonAutoDetect`, visibility mặc định, `MapperFeature.USE_ANNOTATIONS` và cấu hình `AnnotationIntrospector` có thể ảnh hưởng đến quá trình này.

Ví dụ, nếu ứng dụng tắt việc sử dụng annotation Jackson, các annotation như `@JsonProperty` hoặc `@JsonIgnore` sẽ không còn được xử lý theo cách thông thường. Khi gặp kết quả khác dự kiến, cần kiểm tra cả cấu hình mapper và việc property có được phát hiện hay không, thay vì chỉ nhìn vị trí đặt annotation.

## 3. Thứ tự ưu tiên khi serialize

Serialization chuyển object Java thành JSON. Jackson cần chọn thành phần cung cấp giá trị của thuộc tính. Thứ tự accessor chính thông thường là:

| Mức ưu tiên | Thành phần |
|---:|---|
| 1 | Getter |
| 2 | Field |

Constructor parameter và setter không phải accessor đọc giá trị chính trong serialization, nhưng annotation của chúng vẫn có thể được xem xét như metadata bổ sung khi Jackson hợp nhất annotation cho logical property.

### 3.1. Getter được ưu tiên hơn field

Ví dụ field và getter cùng có `@JsonProperty`:

```java
public class Account {
    @JsonProperty("field_name")
    private String name;

    @JsonProperty("getter_name")
    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
```

Khi Jackson nhận diện hai thành phần này là cùng logical property và cả hai cùng cung cấp một annotation type có giá trị xung đột, getter là nguồn ưu tiên trong ngữ cảnh serialization. Tuy nhiên, đặt hai tên JSON khác nhau cho cùng một property là cấu hình khó hiểu và có thể làm quá trình gom property hoặc kết quả theo hướng đọc/ghi trở nên khó dự đoán.

Không nên dùng xung đột tên như một kỹ thuật điều khiển API. Hãy đặt một tên JSON thống nhất cho property, hoặc chủ động thiết kế read/write contract riêng bằng các annotation phù hợp.

### 3.2. Field là nguồn dự phòng khi không có getter

Nếu class không có getter được nhận diện, field có thể là thành phần cung cấp giá trị khi serialize:

```java
public class ApiKey {
    @JsonProperty("key")
    private String value;

    public ApiKey(String value) {
        this.value = value;
    }
}
```

Ở đây, `@JsonProperty` giúp Jackson nhận diện field và dùng tên JSON `key`, kể cả khi field không phải public theo visibility mặc định. Khả năng truy cập và cách phát hiện thành phần còn phụ thuộc cấu hình Jackson và module Java đang sử dụng.

## 4. Thứ tự ưu tiên khi deserialize

Deserialization chuyển JSON thành object Java. Jackson cần chọn thành phần nhận giá trị hoặc tạo object. Thứ tự mutator/creator chính thường là:

| Mức ưu tiên | Thành phần | Vai trò |
|---:|---|---|
| 1 | Tham số creator | Truyền giá trị vào constructor hoặc factory method được Jackson chọn |
| 2 | Setter | Gán giá trị thông qua phương thức setter |
| 3 | Field | Gán trực tiếp vào field có thể truy cập |
| 4 | Getter | Phương án sau cùng trong những trường hợp Jackson cho phép dùng getter như mutator, thường liên quan collection/map có thể sửa đổi |

Thứ tự này mô tả lựa chọn thành phần chính khi các accessor cùng đại diện một property. Việc thực tế Jackson có thể deserialize property hay không còn phụ thuộc constructor, visibility, mutability, annotation và cấu hình liên quan.

### 4.1. Setter được ưu tiên hơn field

```java
public class Account {
    @JsonProperty("field_value")
    private String name;

    public String getName() {
        return name;
    }

    @JsonProperty("setter_value")
    public void setName(String name) {
        this.name = name;
    }
}
```

Khi deserialize và setter là mutator được chọn, metadata từ setter có độ ưu tiên cao hơn field. Ví dụ này cố ý đặt hai tên khác nhau để minh họa xung đột; trong code ứng dụng, nên giữ tên nhất quán giữa field và setter.

Nếu setter không tồn tại hoặc không được Jackson nhận diện, field có thể trở thành mutator. Ví dụ field private có thể được dùng theo annotation hoặc visibility được cấu hình:

```java
public class Account {
    @JsonProperty("name")
    private String name;
}
```

### 4.2. Creator parameter được ưu tiên trước setter

Với class bất biến, Jackson thường nhận dữ liệu qua constructor hoặc factory method. Nếu property được khai báo trong creator, tham số tương ứng là thành phần quan trọng cho quá trình deserialize:

```java
public class Customer {
    private String name;

    @JsonCreator
    public Customer(@JsonProperty("name") String name) {
        this.name = name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
```

Khi tạo `Customer` từ JSON, Jackson có thể truyền giá trị `name` vào constructor được đánh dấu `@JsonCreator`. Việc setter cũng tồn tại không có nghĩa setter luôn được dùng thay cho creator parameter. Creator parameter có mức ưu tiên cao hơn trong việc chọn mutator cho property.

Điều này đặc biệt quan trọng với record và immutable DTO: constructor parameter hoặc record component có thể là con đường chính để tạo object, trong khi không có setter nào để gán lại giá trị sau khi tạo.

## 5. Annotation được hợp nhất theo hướng xử lý

Jackson không chỉ chọn một thành phần rồi bỏ qua toàn bộ thành phần còn lại. Với một logical property, annotation có thể được hợp nhất từ nhiều accessor. Thành phần được ưu tiên sẽ là nguồn chính; annotation từ thành phần khác có thể bổ sung metadata khi annotation type đó chưa được cung cấp ở nguồn ưu tiên.

Có thể ghi nhớ thứ tự nguồn chính như sau:

```text
SERIALIZATION
    getter
      ↓
    field
      ↓
    constructor parameter / setter (metadata bổ sung)

DESERIALIZATION
    creator parameter
      ↓
    setter
      ↓
    field
      ↓
    getter (fallback phù hợp)
```

Khi cùng một annotation type xuất hiện ở nhiều thành phần và các giá trị xung đột, nguồn có độ ưu tiên cao hơn trong hướng xử lý đó thường quyết định metadata được dùng. Khi annotation khác nhau xuất hiện ở các thành phần, chúng có thể cùng tồn tại; ý nghĩa cuối cùng phụ thuộc vào từng annotation và giai đoạn Jackson sử dụng metadata.

Không nên suy rộng thứ tự trên thành quy tắc rằng “mọi annotation đều luôn thắng theo một bảng duy nhất”. Một số annotation có ngữ nghĩa đặc biệt, một số chỉ áp dụng cho serialization hoặc deserialization, và một số được xử lý bằng logic chuyên biệt thay vì chỉ chọn một giá trị đơn.

## 6. Ví dụ về @JsonFormat trên field, getter và setter

`@JsonFormat` là ví dụ dễ quan sát vì định dạng ngày có thể khác nhau giữa đọc và ghi. Để xử lý `LocalDate`, cần dependency `jackson-datatype-jsr310` và đăng ký `JavaTimeModule`.

```java
public class Booking {
    @JsonFormat(pattern = "yyyy-MM-dd")
    private LocalDate date;

    @JsonFormat(pattern = "dd/MM/yyyy")
    public LocalDate getDate() {
        return date;
    }

    @JsonFormat(pattern = "MM-dd-yyyy")
    public void setDate(LocalDate date) {
        this.date = date;
    }
}
```

Với các accessor được Jackson nhận diện là cùng property `date`:

- Khi serialize, getter là accessor chính nên định dạng trên getter được ưu tiên.
- Khi deserialize, setter là mutator chính nên định dạng trên setter được ưu tiên.
- Annotation trên field có thể cung cấp metadata khi thành phần ưu tiên của hướng xử lý tương ứng không khai báo annotation đó.

Ví dụ minh họa reader/writer theo hai hướng:

```java
ObjectMapper mapper = new ObjectMapper()
        .registerModule(new JavaTimeModule());

ObjectReader bookingReader = mapper.readerFor(Booking.class);
ObjectWriter bookingWriter = mapper.writerFor(Booking.class);

Booking booking = bookingReader.readValue(
        "{\"date\":\"12-31-2026\"}"
);

String json = bookingWriter.writeValueAsString(booking);
```

Trong ví dụ này, reader xử lý ngày theo annotation của setter và writer định dạng ngày theo annotation của getter. Đây là lý do cần đánh giá annotation theo từng hướng serialize/deserialize, thay vì chỉ hỏi “annotation nào nằm gần field hơn?”.

Khi đưa ví dụ này vào project thực tế, hãy bảo đảm getter/setter có cùng tên property theo quy ước Jackson và không có naming strategy hoặc mix-in làm thay đổi cách gom property.

## 7. Annotation đặc biệt: @JsonIgnore và @JsonProperty

`@JsonIgnore` có ngữ nghĩa ở cấp property. Khi đặt trên một accessor của property có nhiều accessor, nó thường có thể khiến property bị bỏ qua ở cả quá trình đọc và ghi. Vì vậy, không nên nghĩ rằng đặt `@JsonIgnore` trên getter chỉ đơn giản là ẩn getter còn field và setter vẫn tự động hoạt động như trước.

Nếu mục tiêu là cho phép chỉ một hướng, nên ưu tiên `@JsonProperty(access = ...)` để diễn đạt rõ hợp đồng:

```java
public class Credential {
    private String password;

    @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
    public String getPassword() {
        return password;
    }

    public void setPassword(String password) {
        this.password = password;
    }
}
```

`WRITE_ONLY` có nghĩa property được nhận khi deserialize JSON vào Java nhưng không được xuất khi serialize Java thành JSON. Ngược lại, `READ_ONLY` có nghĩa property được xuất khi serialize nhưng không được nhận để ghi vào object khi deserialize.

Nếu cần tách rõ getter và setter theo hai hướng, Jackson cũng hỗ trợ mô hình split property bằng cách kết hợp `@JsonIgnore` ở một accessor với `@JsonProperty` ở accessor còn lại. Tuy nhiên, cách này cần được dùng có chủ đích và kiểm thử cả hai chiều. `JsonProperty.Access` thường dễ đọc hơn khi mục tiêu chỉ là quy định read-only hoặc write-only.

## 8. Tên thuộc tính tường minh và xung đột tên

`@JsonProperty("...")` có thể xác định tên JSON bên ngoài của một property. Nếu field, getter, setter hoặc creator parameter cùng đại diện một property, hãy giữ tên tường minh nhất quán:

```java
public class Profile {
    @JsonProperty("display_name")
    private String displayName;

    @JsonProperty("display_name")
    public String getDisplayName() {
        return displayName;
    }

    @JsonProperty("display_name")
    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
```

Không nên đặt `@JsonProperty("field_name")` trên field và `@JsonProperty("getter_name")` trên getter chỉ để dựa vào ưu tiên accessor. Tên tường minh khác nhau có thể làm thay đổi cách Jackson nhận diện hoặc tách property, khiến output và input không còn thể hiện cùng một hợp đồng.

Nếu API cần chấp nhận nhiều tên đầu vào nhưng chỉ xuất một tên chuẩn, hãy dùng `@JsonAlias` cho các tên thay thế khi deserialize:

```java
public class Profile {
    @JsonProperty("display_name")
    @JsonAlias({"name", "full_name"})
    private String displayName;
}
```

Trong ví dụ, `display_name` là tên property chuẩn; `name` và `full_name` là alias có thể được chấp nhận khi đọc. Alias không tạo ra nhiều tên output khi serialize.

## 9. Các yếu tố khác có thể ảnh hưởng đến kết quả

Thứ tự accessor là nguyên tắc quan trọng, nhưng kết quả cuối cùng còn chịu ảnh hưởng của những cấu hình khác:

- **Visibility:** field/getter/setter có được Jackson phát hiện hay không. `@JsonAutoDetect` và visibility checker có thể thay đổi tập accessor.
- **Naming strategy:** tên Java như `firstName` có thể được ánh xạ thành `first_name`; đây là bước đặt tên, không phải thứ tự ưu tiên accessor.
- **Annotation introspector:** mapper có thể dùng Jackson annotation, custom introspector hoặc cặp introspector để đọc metadata.
- **Mix-in:** annotation từ mix-in có thể bổ sung hoặc thay thế metadata cho kiểu mà ứng dụng không thể sửa trực tiếp.
- **Feature và module:** cấu hình module, custom serializer/deserializer và feature có thể ảnh hưởng cách annotation được diễn giải.
- **Hướng xử lý:** cùng một property có thể chọn getter khi serialize và setter/creator khi deserialize.

Vì vậy, khi kết quả thực tế khác dự đoán, hãy kiểm tra property được phát hiện như thế nào, kiểu đích là gì, hướng xử lý nào đang chạy và mapper đang dùng cấu hình nào.

## 10. Cách thiết kế annotation để tránh xung đột

Một số nguyên tắc giúp model dễ đọc và tránh phụ thuộc vào thứ tự ưu tiên ngầm:

1. Đặt `@JsonProperty` nhất quán cho các accessor của cùng một property khi cần tên JSON tường minh.
2. Chỉ đặt annotation ở thành phần có chủ đích. Nếu annotation chỉ điều khiển output, ưu tiên getter hoặc cấu hình serialization phù hợp; nếu chỉ điều khiển input, ưu tiên setter/creator hoặc cấu hình deserialization phù hợp.
3. Với class bất biến, khai báo creator rõ ràng và dùng tên tham số phù hợp với JSON contract.
4. Với property chỉ đọc hoặc chỉ ghi, cân nhắc `@JsonProperty(access = READ_ONLY/WRITE_ONLY)` thay vì kết hợp nhiều annotation gây khó hiểu.
5. Tránh đặt cùng annotation type với giá trị xung đột trên field, getter, setter và constructor parameter.
6. Khi buộc phải dùng mix-in hoặc custom introspector, ghi rõ mục đích và có test cho cả serialize lẫn deserialize.

## 11. Kiểm tra kết quả ở cả hai chiều

Khi một property có nhiều accessor hoặc annotation, một test chỉ kiểm tra serialize có thể bỏ sót hành vi deserialize khác biệt. Nên kiểm tra cả JSON được tạo ra và object được tạo từ JSON.

Ví dụ kiểm tra tên property và định dạng ngày:

```java
ObjectMapper mapper = new ObjectMapper()
        .registerModule(new JavaTimeModule());

ObjectReader reader = mapper.readerFor(Booking.class);
ObjectWriter writer = mapper.writerFor(Booking.class);

Booking booking = reader.readValue(
        "{\"date\":\"12-31-2026\"}"
);

String output = writer.writeValueAsString(booking);
JsonNode tree = mapper.readTree(output);

assertEquals("31/12/2026", tree.get("date").asText());
```

Test cần phản ánh hợp đồng mà ứng dụng mong muốn. Nếu property được thiết kế write-only, test phải xác nhận JSON đầu vào có thể gán giá trị và JSON đầu ra không chứa property đó. Nếu tên JSON có alias, test nên xác nhận alias được nhận khi đọc nhưng tên chuẩn được dùng khi ghi.

Khi muốn xem Jackson đang chọn property và accessor nào, có thể bật logging phù hợp cho quá trình introspection hoặc dùng test nhỏ với JSON đầu vào/đầu ra cụ thể. Đừng dựa vào việc in object Java để kết luận annotation đã được áp dụng đúng; hãy quan sát JSON thực tế.

## 12. Ghi nhớ

Khi annotation xuất hiện trên nhiều thành phần của cùng logical property, Jackson hợp nhất metadata và chọn accessor chính theo hướng xử lý. Serialization thường ưu tiên getter rồi đến field; deserialization thường ưu tiên creator parameter, setter rồi đến field, với getter là fallback trong trường hợp phù hợp. Annotation ở accessor ưu tiên cao hơn có thể quyết định giá trị khi cùng annotation type xung đột, nhưng từng annotation vẫn có quy tắc riêng.

Để tránh hành vi khó đoán, hãy thống nhất tên property giữa các accessor, đặt annotation ở đúng hướng sử dụng, dùng `JsonProperty.Access` cho thuộc tính read-only/write-only và kiểm tra cả serialize lẫn deserialize. Khi hiểu cách Jackson gom property và chọn accessor, việc đặt annotation trở nên có chủ đích thay vì dựa vào phỏng đoán.
