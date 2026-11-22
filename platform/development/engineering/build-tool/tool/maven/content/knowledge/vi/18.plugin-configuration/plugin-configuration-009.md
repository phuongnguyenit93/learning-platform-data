# Phân biệt tham số bắt buộc, giá trị mặc định và tham số chỉ đọc trong Maven plugin

Một Maven goal có thể có nhiều tham số cấu hình: tên file đầu vào, đường dẫn output, mức độ nghiêm ngặt, nhóm mục tiêu hoặc một giá trị suy ra từ POM. Khi đọc tài liệu plugin, bạn thường gặp ba nhãn **Required**, **Default** và **Read-only**. Ba nhãn này trả lời **ba câu hỏi khác nhau**, chứ không phải ba loại giá trị loại trừ nhau:

- **Bắt buộc (`required=true`):** Maven cần một giá trị phù hợp để cấu hình Mojo trước khi gọi goal. Nếu tham số không được cung cấp/không thể inject, goal có thể thất bại vì cấu hình thiếu.
- **Giá trị mặc định (`defaultValue`):** plugin cung cấp giá trị dự phòng hoặc một biểu thức để Maven đánh giá khi chuẩn bị tham số. Tham số vẫn có thể được ghi đè nếu plugin cho phép và có nguồn cấu hình có ưu tiên thích hợp.
- **Chỉ đọc (`readonly=true`):** người sử dụng **không được cấu hình trực tiếp tham số đó trong cấu hình plugin**; giá trị thường được Maven suy ra từ mô hình dự án hoặc runtime context. Nó **không đồng nghĩa với `final` trong Java, không phải giới hạn quyền hệ điều hành và không phải cơ chế che giấu bí mật**.

Ví dụ điển hình bằng Maven Plugin Tools annotations:

```java
@Parameter(property = "lesson.recipient", required = true)
private String recipient;

@Parameter(property = "lesson.greeting", defaultValue = "Hello")
private String greeting;

@Parameter(defaultValue = "${project.build.finalName}", readonly = true)
private String finalName;
```

Trong cùng một Mojo:
- `recipient` yêu cầu một người nhận; có thể đến từ XML `<recipient>` hoặc user property `-Dlesson.recipient=...` khi được hỗ trợ.
- `greeting` mặc định là `Hello`; nếu không cấu hình, goal dùng giá trị này.
- `finalName` lấy từ `project.build.finalName` trong mô hình Maven; người dùng nên đổi **`<build><finalName>...`** trong POM nếu muốn đổi tên artifact, thay vì cố sửa `<finalName>` trong `<plugin><configuration>`.

Bài này giải thích annotation, metadata trong plugin descriptor, các nguồn giá trị (`pom.xml`, `-D`, expressions), cách kiểm chứng bằng `help:describe` và một lab Java 17 để quan sát ba cơ chế khi chạy một Maven plugin tự viết.

## 1. Tham số Maven plugin là gì?

Plugin goal được thực thi bởi **Mojo** (*Maven plain Old Java Object*), một class Java thực hiện logic build. Thông thường với Maven 3, một Mojo kế thừa `org.apache.maven.plugin.AbstractMojo` và cung cấp `execute()`.

Người viết plugin có thể khai báo các field được Maven inject:

```java
@Parameter(property = "lesson.recipient", required = true)
private String recipient;
```

Maven Plugin Tools đọc annotations khi build plugin, sinh metadata trong **`META-INF/maven/plugin.xml`**. Khi người dùng gọi goal, Maven dùng plugin descriptor và cấu hình có hiệu lực để điền giá trị field trước khi gọi `execute()`.

Một tham số có nhiều thuộc tính:

| Thuộc tính annotation | Mục đích | Mặc định của annotation |
| --- | --- | --- |
| `name` | Tên tham số (nếu khác tên field Java). | Chuỗi rỗng, tức sử dụng tên field theo cơ chế plugin tools. |
| `alias` | Tên cấu hình thay thế được hỗ trợ. | Chuỗi rỗng. |
| `property` | Tên property Maven có thể được dùng để cung cấp giá trị. | Chuỗi rỗng. |
| `defaultValue` | Giá trị hoặc expression dự phòng, đánh giá khi injection. | Chuỗi rỗng. |
| `required` | Có phải tham số bắt buộc khi cấu hình Mojo không? | `false`. |
| `readonly` | Có cấm cấu hình trực tiếp bởi người dùng không? | `false`. |

Tài liệu chính thức `org.apache.maven.plugins.annotations.Parameter` của Maven Plugin Tools 3.16.0 xác nhận cả `required`, `readonly`, `property` và `defaultValue` là các phần tử độc lập. Vì vậy một tham số **có thể vừa required, vừa có defaultValue**; hoặc **vừa readonly, vừa dựa vào defaultValue là expression**.

**Chú ý:** “default của annotation là chuỗi rỗng” không có nghĩa mọi field Java kiểu `String` luôn nhận chuỗi rỗng. Nếu không có nguồn cấu hình, giá trị Java có thể vẫn là `null`; cách Maven Plugin Tools mô tả metadata và inject một tham số còn phụ thuộc annotation và loại dữ liệu.

## 2. Bảng so sánh required, defaultValue và readonly

| Câu hỏi | `required=true` | `defaultValue="..."` | `readonly=true` |
| --- | --- | --- | --- |
| Giải quyết vấn đề gì? | Tránh chạy goal khi thiếu cấu hình cần thiết. | Cung cấp giá trị khi người dùng không cấu hình. | Ngăn cấu hình trực tiếp một giá trị được hệ thống quản lý. |
| Có yêu cầu POM phải khai báo giá trị không? | **Không nhất thiết**; có thể đến từ nguồn khác. | Không. | Thường không; giá trị lấy từ context/model. |
| Có thể đi cùng hai thuộc tính kia không? | Có. | Có. | Có, nếu thiết kế đúng. |
| Có phải kiểm tra logic dữ liệu không? | Không; vẫn cần kiểm tra rỗng, định dạng, quyền... | Không; giá trị mặc định cũng có thể không hợp lệ trong môi trường cụ thể. | Không; readonly không bảo vệ file/secret. |
| Metadata tương ứng | `required` của parameter descriptor. | Thuộc tính cấu hình như `default-value`. | `editable=false` của parameter descriptor. |
| Khi nào thường dùng? | Path hoặc giá trị bắt buộc cho goal. | Encoding, greeting, skip flag, build directory... | `project.build.finalName`, thư mục build suy ra từ Maven model. |

Ví dụ ứng dụng phân tích tài liệu:
- Goal `analyze` **bắt buộc** phải biết file đầu vào.
- Mức độ cảnh báo có thể **mặc định** là `normal`.
- Đường dẫn `project.build.directory` có thể được plugin xem là **chỉ đọc** nếu tác giả muốn người dùng cấu hình thư mục output chuẩn của project, không truyền một value không khớp model.

Cách hiểu đúng là **một tham số có nhiều đặc tính**. Không nên đặt nhãn “required parameter” đối lập với “readonly parameter”: chúng có thể đồng thời đúng.

## 3. `required=true`: Maven cần giá trị trước khi thực thi goal

Annotation:

```java
@Parameter(property = "lesson.recipient", required = true)
private String recipient;
```

chỉ ra `recipient` là tham số bắt buộc. Khi Maven không thể xác định/inject giá trị theo metadata và cách cấu hình goal, quá trình cấu hình Mojo có thể thất bại **trước khi `execute()` được gọi**.

Có ít nhất hai cách cấp giá trị:

**Qua `<configuration>` trong POM consumer:**

```xml
<plugin>
    <groupId>org.example.training</groupId>
    <artifactId>parameter-demo-maven-plugin</artifactId>
    <version>1.0.0</version>
    <configuration>
        <recipient>Maven</recipient>
    </configuration>
</plugin>
```

**Qua user property của một invocation thích hợp:**

```bash
mvn org.example.training:parameter-demo-maven-plugin:1.0.0:say -Dlesson.recipient=CLI
```

Ví dụ lệnh thứ hai chỉ chạy khi plugin đã được install/publish và có một POM/ngữ cảnh phù hợp; lab hoàn chỉnh sẽ có ở phần sau.

### 3.1. Required không có nghĩa “bắt buộc người dùng gõ vào XML”

Nguồn giá trị có thể gồm:
- `<configuration>` ở cấp plugin hoặc execution trong POM.
- User property `-Dlesson.recipient=...` khi annotation/descriptor khai báo property.
- Property ở POM hoặc môi trường được tham chiếu qua expression phù hợp.
- `defaultValue` có giá trị hoặc expression đánh giá ra dữ liệu hợp lệ.
- Cấu hình được kế thừa qua parent/pluginManagement hoặc profile khi được áp dụng.

Vì vậy, một field được đánh dấu `required=true` **có thể không cần dòng `<recipient>` trong consumer POM** nếu đã có nguồn cấu hình khác.

### 3.2. Required không thay thế kiểm tra hợp lệ nghiệp vụ

Giả sử người dùng cung cấp:

```xml
<configuration>
    <recipient>   </recipient>
</configuration>
```

Tùy cách injection/trim và kiểm tra, Maven có thể coi trường đã nhận một chuỗi, nhưng giá trị toàn khoảng trắng **không đáp ứng nghiệp vụ**. Plugin vẫn nên kiểm tra:

```java
if (recipient == null || recipient.isBlank()) {
    throw new MojoFailureException("recipient must not be blank");
}
```

`String.isBlank()` có từ Java 11, sử dụng được ở Java 17. Lỗi dạng `MojoFailureException` giúp phân biệt vi phạm đầu vào của người dùng với lỗi kỹ thuật khiến goal không hoàn thành.

Với kiểu số hoặc đường dẫn, required cũng không kiểm tra được mọi quy tắc: file có tồn tại, đường dẫn có nằm trong vùng được phép, version có hỗ trợ, dữ liệu có xung đột nhau không. Cần kiểm tra trong `execute()` hoặc lớp validation thích hợp.

### 3.3. Required và defaultValue cùng tồn tại

```java
@Parameter(required = true, defaultValue = "public")
private String channel;
```

Nếu không có cấu hình khác, `channel` thường nhận `public`, vì thế điều kiện required đã có nguồn giá trị. Đây **không phải mâu thuẫn cú pháp**, nhưng hãy tự hỏi có thật sự muốn người dùng phải cung cấp tham số hay không.

- Nếu **bắt buộc người dùng quyết định**, thông thường **không đưa defaultValue có thể tự đáp ứng required**.
- Nếu **muốn luôn có một giá trị**, defaultValue có thể hữu ích; `required=true` đôi khi chỉ là chốt kiểm tra sau expression.
- Nếu defaultValue là `${some.missing.property}`, đừng mặc định mọi expression đều resolve thành giá trị sử dụng được; kiểm tra kết quả và thông báo lỗi rõ ràng.

Không thêm `required=true` vào mọi field chỉ để “cho an toàn”; điều đó làm metadata khó hiểu và có thể tạo lỗi cấu hình không cần thiết.

## 4. `defaultValue`: giá trị dự phòng, không phải giá trị bất biến

Ví dụ:

```java
@Parameter(property = "lesson.greeting", defaultValue = "Hello")
private String greeting;
```

Nếu không có nguồn cấu hình nào khác, Maven có thể inject chuỗi `Hello`. Người dùng có thể thay đổi bằng cách được plugin hỗ trợ:

```bash
mvn ... -Dlesson.greeting=Welcome
```

Dấu `...` ở đây viết tắt cho **goal và POM đã xác định**, không phải lệnh có thể copy nguyên. Lab ở phần 8 sẽ đưa các lệnh đầy đủ.

### 4.1. DefaultValue có thể là expression

```java
@Parameter(defaultValue = "${project.build.directory}")
private java.io.File outputDirectory;
```

PluginParameterExpressionEvaluator của Maven đánh giá biểu thức trong ngữ cảnh project/goal khi inject. Biểu thức `${project.build.directory}` không có nghĩa chữ literal đó sẽ luôn đi vào Java field; nó có thể được chuyển thành đường dẫn build directory của project.

Ví dụ khác:

```java
@Parameter(defaultValue = "${project.build.finalName}", readonly = true)
private String finalName;
```

Đây là trường **vừa có defaultValue là expression, vừa readonly**. Người dùng có thể thay giá trị nguồn ở mô hình project:

```xml
<build>
    <finalName>consumer-release</finalName>
</build>
```

Tham số readonly `finalName` khi được inject sẽ theo `project.build.finalName` của project phù hợp, thay vì yêu cầu người dùng cấu hình tham số trực tiếp trong plugin.

### 4.2. `defaultValue` và `property` không giống nhau

```java
@Parameter(property = "lesson.greeting", defaultValue = "Hello")
private String greeting;
```

`property` là **tên kênh cấu hình**; `defaultValue` là **giá trị dự phòng**.

Bảng tình huống minh họa khi không có cấu hình POM tường minh đè lên tham số:

| Nguồn được thiết lập | Giá trị kỳ vọng trong Mojo |
| --- | --- |
| Không có `lesson.greeting` | `Hello`. |
| CLI có `-Dlesson.greeting=Welcome` | `Welcome`. |
| CLI có `-Dlesson.greeting=Bonjour` | `Bonjour`. |
| POM cấu hình trực tiếp `<greeting>Hi</greeting>` | `Hi` trong ngữ cảnh POM đó. |

Không suy ra một quy tắc ưu tiên duy nhất cho **mọi loại cấu hình** bằng việc nhìn bảng này. Maven kết hợp thông tin từ plugin descriptor, plugin-level/execution-level configuration, properties và default values. Khi POM đã chỉ định `<greeting>Hi</greeting>` tường minh, việc thêm `-Dlesson.greeting=Welcome` **không nên được giả định chắc chắn sẽ thắng** mà không xem cấu hình Mojo thực tế. Để ưu tiên CLI khi thiết kế plugin, tài liệu nên nêu rõ channel được hỗ trợ và có test cho hành vi đó.

### 4.3. Giá trị mặc định được chuyển theo kiểu Java

Các ví dụ:

```java
@Parameter(property = "lesson.enabled", defaultValue = "true")
private boolean enabled;

@Parameter(property = "lesson.maxItems", defaultValue = "10")
private int maxItems;

@Parameter(defaultValue = "${project.build.directory}")
private java.io.File directory;
```

Dù annotation `defaultValue` là `String`, Maven chuyển đổi sang kiểu field phù hợp khi inject. Với kiểu phức tạp như `List`, `Map`, XML nested objects hoặc đường dẫn, cách cấu hình có thể phức tạp hơn; không lấy chuỗi trong tài liệu làm bằng chứng rằng mọi định dạng đều hợp lệ cho mọi kiểu.

Nếu người dùng cung cấp `-Dlesson.maxItems=abc` cho field `int`, việc chuyển kiểu có thể gây lỗi cấu hình trước khi Mojo chạy. Nếu `maxItems` phải lớn hơn 0, plugin vẫn cần kiểm tra nghiệp vụ.

## 5. `readonly=true`: không cho cấu hình trực tiếp tham số

Theo API chính thức của Maven Plugin Tools 3.16.0, `readonly=true` diễn đạt **tham số không được cấu hình trực tiếp bởi người dùng**, đặc biệt thông qua POM plugin `<configuration>`.

Ví dụ:

```java
@Parameter(
    defaultValue = "${project.build.finalName}",
    readonly = true
)
private String finalName;
```

Giá trị nằm trong **mô hình Maven project**. Nếu cần đổi nó, cách hợp lý là chỉnh:

```xml
<build>
    <finalName>consumer-release</finalName>
</build>
```

thay vì cố ghi:

```xml
<plugin>
    <groupId>org.example.training</groupId>
    <artifactId>parameter-demo-maven-plugin</artifactId>
    <version>1.0.0</version>
    <configuration>
        <finalName>override-directly</finalName>
    </configuration>
</plugin>
```

Đoạn cuối là **anti-pattern để nhận diện**, không phải lời khuyên áp dụng. Plugin descriptor đánh dấu parameter này không chỉnh trực tiếp; thông báo lỗi/cảnh báo hoặc việc bỏ qua giá trị có thể thay đổi theo Maven/plugin tooling. **Không dựa vào kết quả của một bản Maven để khẳng định mọi phiên bản sẽ xử lý cú pháp sai theo cùng một cách.**

### 5.1. Readonly không đồng nghĩa Java `final`

Các khái niệm không liên quan trực tiếp:

| Khái niệm | Nó bảo vệ điều gì? |
| --- | --- |
| `@Parameter(readonly = true)` | Giao diện cấu hình plugin: hạn chế cấu hình tham số trực tiếp. |
| `private final String name` trong Java | Field Java không được gán lại sau khởi tạo theo luật ngôn ngữ; không phải Maven parameter flag. |
| File system read-only/ACL | Quyền ghi file/thư mục của process. |
| Maven repository release immutability | Chính sách lưu artifact release không bị ghi đè. |
| CI secret masking | Cơ chế hạn chế lộ secret trong log, không do `readonly` cung cấp. |

Không khai báo field Maven parameter thành `final` chỉ vì muốn nó readonly. Maven cần cơ chế injection phù hợp, có thể yêu cầu field khả ghi khi cấu hình Mojo. Readonly của plugin metadata **không phải bất biến của đối tượng Java**.

### 5.2. Readonly không phải rào cản bảo mật

Nếu thông tin lấy từ `${project.build.finalName}`, người chỉnh POM build vẫn có thể đổi giá trị nguồn của expression. Với những expression liên quan cấu hình hệ thống/môi trường, nguồn của giá trị có thể do những cấu hình khác chi phối.

`readonly=true` không ngăn:
- Mã Java trong Mojo ghi đè field của chính nó.
- Người có quyền sửa POM thay phần tử model nguồn.
- Người quản trị thay settings/JDK/environment.
- Secret bị in qua `getLog()` hoặc thông tin debug.
- Một plugin khác thay đổi state dự án trước đó.

Dùng readonly để **thiết kế API plugin nhất quán**, không dùng để bảo vệ credentials, áp đặt quyền hay chống sửa dữ liệu độc hại.

### 5.3. Readonly và Maven-provided objects

Plugin cũ đôi khi có:

```java
@Parameter(defaultValue = "${project}", readonly = true)
private org.apache.maven.project.MavenProject project;
```

Đây là **đoạn Java minh họa ngữ cảnh Maven 3**, không phải file độc lập. Tài liệu Maven Plugin Tools có ví dụ truyền đối tượng Maven context qua expressions rồi đánh dấu readonly. Với plugin Maven 3 phiên bản mới, nhiều trường hợp nên dùng Maven APIs/JSR-330 injection thích hợp theo tài liệu thay vì phụ thuộc vào mọi pseudo-parameter expression cũ. Nhưng mục đích `readonly` vẫn là không để người dùng cung cấp một object giả bằng XML tùy ý.

## 6. Từ annotations sang metadata trong `plugin.xml`

Khi Maven Plugin Plugin chạy goal `plugin:descriptor`, Plugin Tools thu thập annotation/Javadoc metadata và sinh **`META-INF/maven/plugin.xml`** trong plugin JAR.

Descriptor của Maven 3 có các nhóm:

```text
plugin
  mojos
    mojo
      goal
      implementation
      parameters
        parameter
          name
          type
          required
          editable
      configuration
        <parameter-name default-value="...">expression</parameter-name>
```

Những giá trị thường có ý nghĩa:

- `required=true` trên annotation tương ứng với `<required>true</required>` của parameter descriptor.
- `readonly=true` tương ứng với **`<editable>false</editable>`** trong descriptor.
- `defaultValue` thường được thể hiện ở **configuration metadata** như thuộc tính `default-value` chứ không phải luôn là một thẻ `<defaultValue>` ngay dưới `<parameter>`.
- `property="lesson.recipient"` là thông tin cách biểu thức/property được dùng để inject; không đồng nghĩa một field Java khác tên mới được tạo.

Một **đoạn XML chỉ để học cấu trúc**, không phải plugin descriptor đầy đủ:

```xml
<parameters>
    <parameter>
        <name>recipient</name>
        <type>java.lang.String</type>
        <required>true</required>
        <editable>true</editable>
    </parameter>
    <parameter>
        <name>finalName</name>
        <type>java.lang.String</type>
        <required>false</required>
        <editable>false</editable>
    </parameter>
</parameters>
<configuration>
    <recipient implementation="java.lang.String">${lesson.recipient}</recipient>
    <greeting implementation="java.lang.String"
              default-value="Hello">${lesson.greeting}</greeting>
    <finalName implementation="java.lang.String"
               default-value="${project.build.finalName}"/>
</configuration>
```

Đoạn trên **cố tình không có root `<plugin>` và một số trường bắt buộc/được sinh**, nên không thể copy thẳng thành `plugin.xml` chạy được. Các phiên bản Plugin Tools có thể tạo XML khác về thứ tự/trường/format. Với plugin thật, **đọc descriptor được sinh** thay vì dựa vào mẫu do người viết bài phỏng đoán.

Sự khác nhau giữa `readonly` ở annotation và `editable` ở descriptor rất đáng nhớ: **`readonly=true` → `editable=false`**. Vì vậy tài liệu/Help Plugin có thể dùng từ “read-only” còn XML metadata dùng “editable”.

## 7. Nguồn cấu hình và mức độ ưu tiên: đọc đúng ngữ cảnh

Một parameter có thể nhận giá trị từ nhiều nơi. Ví dụ project consumer có:

```xml
<build>
    <finalName>consumer-release</finalName>
    <plugins>
        <plugin>
            <groupId>org.example.training</groupId>
            <artifactId>parameter-demo-maven-plugin</artifactId>
            <version>1.0.0</version>
            <configuration>
                <recipient>Maven</recipient>
            </configuration>
        </plugin>
    </plugins>
</build>
```

- `recipient` được cấu hình trực tiếp từ `<configuration>`.
- `greeting` không có cấu hình POM, nên có thể nhận default `Hello`.
- `finalName` là read-only parameter có expression đọc `project.build.finalName`, kết quả là `consumer-release` ở context POM này.

Nếu chuyển `<configuration>` vào `<execution>`, chỉ những goal invocation gắn với execution đó mới sử dụng cấu hình tương ứng theo cơ chế Maven; gọi goal trực tiếp có thể dùng execution ID `default-cli` thay vì execution đã định nghĩa. Do đó **không giả định** mọi goal invocation có cấu hình giống nhau khi một project chứa nhiều executions.

Có thể có:
- Cấu hình cấp plugin.
- Cấu hình riêng từng execution.
- Cấu hình quản lý/kế thừa từ parent hoặc `pluginManagement`.
- Profile kích hoạt theo `-P` hoặc môi trường.
- User properties `-D...` và POM properties.
- Default expressions trong descriptor.
- Maven project model và runtime objects.

**Không có một câu “CLI luôn thắng POM” đúng cho mọi plugin parameter.** Ví dụ nếu người dùng viết trực tiếp `<greeting>Hi</greeting>` trong cấu hình có hiệu lực, property `lesson.greeting` có thể không được dùng như họ dự đoán. Muốn biết thực tế, xem POM có hiệu lực và thử với lệnh/goal đúng; khi viết plugin của riêng mình, tạo test cho từng kênh cấu hình mà bạn công bố.

## 8. Lab Java 17: plugin có required, default và readonly

Lab này tạo một Maven plugin nhỏ với goal `say`. Nó minh họa cả ba đặc tính bằng hành vi quan sát được.

Yêu cầu:
- JDK 17 trở lên.
- Maven 3.x phù hợp với Maven Plugin Tools/Compiler Plugin được ghim dưới đây.
- Máy có thể tải plugin dependencies từ repository hợp lệ nếu local cache chưa có.
- Quyền ghi local Maven repository để `mvn install` plugin.

Tất cả tọa độ `org.example.training` và project consumer là dữ liệu học tập, không được ngầm coi là artifact đã có trên Maven Central.

### 8.1. Sơ đồ project

```text
parameter-lab/
├── parameter-demo-maven-plugin/
│   ├── pom.xml
│   └── src/main/java/org/example/training/mojo/SayMojo.java
└── demo-consumer/
    └── pom.xml
```

Không có root aggregator POM. Khi đứng trong `parameter-lab`, các lệnh dùng `-f` để chọn đúng project.

Linux/macOS:

```bash
mkdir -p parameter-lab/parameter-demo-maven-plugin/src/main/java/org/example/training/mojo
mkdir -p parameter-lab/demo-consumer
cd parameter-lab
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path "parameter-lab/parameter-demo-maven-plugin/src/main/java/org/example/training/mojo" | Out-Null
New-Item -ItemType Directory -Force -Path "parameter-lab/demo-consumer" | Out-Null
Set-Location parameter-lab
```

### 8.2. POM plugin hoàn chỉnh

Tệp `parameter-demo-maven-plugin/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example.training</groupId>
    <artifactId>parameter-demo-maven-plugin</artifactId>
    <version>1.0.0</version>
    <packaging>maven-plugin</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <maven.plugin.tools.version>3.16.0</maven.plugin.tools.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.maven</groupId>
            <artifactId>maven-plugin-api</artifactId>
            <version>3.9.9</version>
            <scope>provided</scope>
        </dependency>
        <dependency>
            <groupId>org.apache.maven.plugin-tools</groupId>
            <artifactId>maven-plugin-annotations</artifactId>
            <version>${maven.plugin.tools.version}</version>
            <scope>provided</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-plugin-plugin</artifactId>
                <version>${maven.plugin.tools.version}</version>
                <configuration>
                    <goalPrefix>parameter-demo</goalPrefix>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Giải thích:

- Packaging `maven-plugin` là Maven plugin project, để lifecycle/Plugin Tools tạo descriptor.
- `maven-plugin-api` cung cấp `AbstractMojo`, `MojoExecutionException` và `MojoFailureException`.
- `maven-plugin-annotations` cung cấp `@Mojo`, `@Parameter` và `LifecyclePhase`.
- Hai dependency API/annotations được đặt `provided` theo thực hành phù hợp cho Maven plugin; chúng không phải dependency ứng dụng consumer.
- `maven-plugin-plugin` version 3.16.0 xử lý metadata Mojo và tạo `META-INF/maven/plugin.xml`.
- `maven.compiler.release=17` cho biết bytecode plugin cần Java 17+, vì plugin chạy trong JVM của Maven.
- `goalPrefix=parameter-demo` dùng cho cơ chế prefix; lab gọi goal bằng GAV đầy đủ để không phụ thuộc prefix discovery.

Không tạo file class `main` cho plugin: Maven sẽ gọi `execute()` của Mojo qua descriptor.

### 8.3. Java Mojo hoàn chỉnh

Tệp `parameter-demo-maven-plugin/src/main/java/org/example/training/mojo/SayMojo.java`:

```java
package org.example.training.mojo;

import org.apache.maven.plugin.AbstractMojo;
import org.apache.maven.plugin.MojoExecutionException;
import org.apache.maven.plugin.MojoFailureException;
import org.apache.maven.plugins.annotations.LifecyclePhase;
import org.apache.maven.plugins.annotations.Mojo;
import org.apache.maven.plugins.annotations.Parameter;

/**
 * A tiny goal that demonstrates three Maven parameter attributes.
 */
@Mojo(name = "say", defaultPhase = LifecyclePhase.VALIDATE, threadSafe = true)
public final class SayMojo extends AbstractMojo {

    /**
     * Required recipient.
     */
    @Parameter(property = "lesson.recipient", required = true)
    private String recipient;

    /**
     * Optional greeting with a default value.
     */
    @Parameter(property = "lesson.greeting", defaultValue = "Hello")
    private String greeting;

    /**
     * The artifact name from the Maven project model.
     * It is not directly configurable as a plugin parameter.
     */
    @Parameter(defaultValue = "${project.build.finalName}", readonly = true)
    private String finalName;

    @Override
    public void execute() throws MojoExecutionException, MojoFailureException {
        if (recipient == null || recipient.isBlank()) {
            throw new MojoFailureException("recipient must not be blank");
        }
        if (finalName == null || finalName.isBlank()) {
            throw new MojoExecutionException("project finalName is missing");
        }

        getLog().info(greeting + ", " + recipient + "!");
        getLog().info("Project finalName: " + finalName);
    }
}
```

Đây là class Java 17+ hoàn chỉnh. Nó có **hai output lines do Mojo ghi log**, không có phương thức `main`. Phương thức `execute()` được Maven gọi sau khi plugin descriptor được đọc và parameters được inject.

Các vai trò:
- `recipient`: required. Nếu không có giá trị, Maven có thể dừng khi cấu hình goal; kiểm tra `isBlank()` trong code còn chống giá trị toàn whitespace khi injection đã diễn ra.
- `greeting`: có default literal `Hello`, có property `lesson.greeting` để thay thế trong trường hợp phù hợp.
- `finalName`: đọc từ `project.build.finalName` và là readonly, tránh cấu hình riêng trực tiếp dẫn đến khác mô hình dự án.
- `getLog().info`: thông điệp xuất hiện trong Maven log; Maven có thể bổ sung prefix `[INFO]` và các dòng khác.

**Lưu ý về output chính xác:** những dòng ví dụ bên dưới chỉ là **nội dung message** do Mojo tạo; không phải toàn bộ stdout/stderr của Maven vì điều đó còn phụ thuộc phiên bản, plugin startup và môi trường.

### 8.4. Build, install và kiểm tra descriptor

Từ thư mục `parameter-lab`:

```bash
mvn -version
mvn -B -ntp -f parameter-demo-maven-plugin/pom.xml clean install
```

Nếu cấu hình và môi trường hợp lệ, Maven tạo plugin JAR và cài vào local repository của máy:

```text
parameter-demo-maven-plugin/target/parameter-demo-maven-plugin-1.0.0.jar
parameter-demo-maven-plugin/target/classes/META-INF/maven/plugin.xml
```

Kiểm tra JAR bằng JDK:

```bash
jar --list --file parameter-demo-maven-plugin/target/parameter-demo-maven-plugin-1.0.0.jar
```

Tìm các entry:

```text
META-INF/maven/plugin.xml
org/example/training/mojo/SayMojo.class
```

Đây là **hai entry tiêu biểu**, không phải toàn bộ danh sách file. Nếu không có descriptor, xem packaging, annotations và việc Maven Plugin Plugin chạy trong lifecycle. File trong `target` là output được sinh; không nên chỉnh tay rồi commit.

### 8.5. Consumer POM hoàn chỉnh

Tệp `demo-consumer/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example.consumer</groupId>
    <artifactId>demo-consumer</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <build>
        <finalName>consumer-release</finalName>

        <plugins>
            <plugin>
                <groupId>org.example.training</groupId>
                <artifactId>parameter-demo-maven-plugin</artifactId>
                <version>1.0.0</version>

                <configuration>
                    <recipient>Maven</recipient>
                </configuration>

                <executions>
                    <execution>
                        <id>say-on-validate</id>
                        <phase>validate</phase>
                        <goals>
                            <goal>say</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

Hãy quan sát ba lựa chọn:

1. **Required:** `recipient` được cung cấp tường minh bằng `<recipient>Maven</recipient>`.
2. **Default:** `greeting` **không** được khai báo trong POM. Plugin sẽ dùng default `Hello`.
3. **Readonly:** `finalName` không nằm trong `<plugin><configuration>`; nó lấy từ `<build><finalName>consumer-release</finalName></build>`.

Đây là cách dùng mô hình Maven phù hợp: khai báo tên artifact ở build model thay vì tạo một cấu hình plugin riêng xung đột với model.

### 8.6. Chạy bằng phase validate

Từ `parameter-lab`:

```bash
mvn -B -ntp -f demo-consumer/pom.xml validate
```

Nếu plugin đã install thành công, log Maven sẽ chứa **đúng hai message** do `SayMojo` ghi:

```text
Hello, Maven!
Project finalName: consumer-release
```

Đây là **nội dung log**, không phải toàn bộ stdout của Maven. Vì phase `validate` đi trước compile/package, consumer chưa cần source code Java để chạy ví dụ và chưa được kỳ vọng có JAR ứng dụng.

### 8.7. Thay đổi default bằng property CLI

Không thêm `<greeting>` tường minh vào POM; từ `parameter-lab`:

```bash
mvn -B -ntp -f demo-consumer/pom.xml validate -Dlesson.greeting=Welcome
```

Thông điệp kỳ vọng:

```text
Welcome, Maven!
Project finalName: consumer-release
```

So với lần trước, chỉ greeting thay đổi. `recipient` vẫn từ POM; `finalName` vẫn từ project model. Trường hợp này minh họa đúng quan hệ **defaultValue vs user property** mà không vướng xung đột với cấu hình `<greeting>` tường minh.

### 8.8. Cấp required qua property thay vì XML

POM plugin tự tạo trong lab **không khai báo `recipient` của chính goal `say`**. Sau khi plugin đã install, có thể dùng POM plugin đó làm ngữ cảnh để gọi goal trực tiếp:

```bash
mvn -B -ntp -f parameter-demo-maven-plugin/pom.xml org.example.training:parameter-demo-maven-plugin:1.0.0:say -Dlesson.recipient=CLI
```

Nội dung message đầu tiên kỳ vọng:

```text
Hello, CLI!
```

Thông điệp thứ hai ghi `Project finalName` của chính **project plugin**, thông thường là tên artifact/version mặc định nếu không có `<finalName>` khác, nên không cố gắng dùng nó như bằng chứng của consumer project.

### 8.9. Quan sát tình huống required bị thiếu

Nếu gọi cùng goal từ POM plugin nhưng **bỏ `-Dlesson.recipient=CLI`**, không có cấu hình `<recipient>` thích hợp:

```bash
mvn -B -ntp -f parameter-demo-maven-plugin/pom.xml org.example.training:parameter-demo-maven-plugin:1.0.0:say
```

Kết quả mong đợi là **build thất bại do tham số bắt buộc không được cấu hình**, thường xảy ra khi Maven chuẩn bị/inject Mojo, trước khi nội dung greeting được thực thi. **Không ghi cố định nguyên văn stderr** vì chi tiết exception thông báo có thể khác theo Maven/Plugin Tools version.

Đây là một **bài test âm tính**: mục tiêu là thấy `required=true` ngăn goal chạy không có dữ liệu đầu vào cần thiết, không phải kiểm tra rằng toàn bộ Maven luôn báo một thông điệp giống hệt.

### 8.10. Đổi read-only qua mô hình POM đúng cách

Trong consumer, thay:

```xml
<finalName>consumer-release</finalName>
```

bằng:

```xml
<finalName>consumer-v2</finalName>
```

Đây là **đoạn XML trong `<build>`**, không phải một POM độc lập. Chạy lại:

```bash
mvn -B -ntp -f demo-consumer/pom.xml validate
```

Messages kỳ vọng:

```text
Hello, Maven!
Project finalName: consumer-v2
```

Field `finalName` của Mojo vẫn được đánh dấu `readonly=true`, nhưng **giá trị nguồn của project model đã đổi**. Ví dụ này chứng minh readonly **không phải bất biến của dữ liệu đầu vào**, mà là ràng buộc cách cấu hình tham số plugin.

## 9. Xem required/default/read-only qua `help:describe`

Dùng goal `help:describe` với `-Ddetail` để đọc metadata của plugin thật:

```bash
mvn -f demo-consumer/pom.xml org.apache.maven.plugins:maven-help-plugin:3.5.2:describe -Dplugin=org.example.training:parameter-demo-maven-plugin:1.0.0 -Dgoal=say -Ddetail
```

Khi plugin được resolve đúng, Help Plugin sẽ mô tả goal `say` và các tham số theo metadata nó có thể hiển thị: type, required, user property, default value và mô tả từ Javadoc/descriptor khi có.

Một số điều cần biết:
- Help Plugin giúp người dùng thấy **hợp đồng cấu hình**, không phải thứ tự đầy đủ của mọi bước inject.
- Metadata dạng “Required: Yes/No” không đồng nghĩa giá trị nào cũng được kiểm tra nghiệp vụ.
- Nếu không tìm thấy thông tin **read-only** trong trình bày của một phiên Help Plugin, hãy xem descriptor `META-INF/maven/plugin.xml`, nơi parameter có `<editable>false</editable>`.
- Không dùng `help:describe` để tiết lộ secrets: metadata có thể chứa đường dẫn, default expressions hoặc thông tin nhạy cảm trong mô tả plugin công ty.

Để kiểm tra các lệnh có sẵn từ Maven Help Plugin:

```bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:describe -Dplugin=org.apache.maven.plugins:maven-compiler-plugin:3.14.1 -Dgoal=compile -Ddetail
```

Lệnh trên dùng plugin công khai, có thể so sánh cách tài liệu chính thức hiển thị `Required`, `Default` và `User Property`. Không khẳng định tất cả plugin đều trình bày thông tin read-only y hệt.

## 10. Kiểm tra trực tiếp plugin descriptor

Sau khi lab build thành công, mở:

```text
parameter-demo-maven-plugin/target/classes/META-INF/maven/plugin.xml
```

Tìm:
- `<goal>say</goal>`.
- `<implementation>org.example.training.mojo.SayMojo</implementation>`.
- `<name>recipient</name>` và `<required>true</required>`.
- `<name>greeting</name>` và cấu hình default `Hello`.
- `<name>finalName</name>` với `<editable>false</editable>`.
- Expression `${project.build.finalName}` trong configuration metadata.

Có thể dùng JDK `jar` để xác minh file đã được đưa vào JAR:

```bash
jar --list --file parameter-demo-maven-plugin/target/parameter-demo-maven-plugin-1.0.0.jar
```

Nếu muốn xem nội dung file XML, dùng editor trên file dưới `target/classes` hoặc giải nén ở thư mục tạm riêng; **không chỉnh nó thủ công**. Maven Plugin Plugin có trách nhiệm tái sinh descriptor từ source và annotations trong build tiếp theo.

**Bẫy:** một plugin JAR có `SayMojo.class` nhưng thiếu descriptor vẫn có thể khiến Maven báo thiếu plugin descriptor. Ngược lại, descriptor có thể tham chiếu implementation class sai nếu artifact bị build/đóng gói bất thường. Vì vậy phải kiểm tra cả class và metadata.

## 11. Khi tham số có kiểu phức tạp hoặc được kế thừa

### 11.1. Boolean với default value

Ví dụ goal chạy optional check:

```java
@Parameter(property = "lesson.skip", defaultValue = "false")
private boolean skip;
```

Plugin có thể dùng:

```java
if (skip) {
    getLog().info("Skipping lesson");
    return;
}
```

Đây là **đoạn mã trong `execute()`**, không phải một class Java độc lập. Người dùng có thể chọn `-Dlesson.skip=true` trong ngữ cảnh phù hợp. Vì kiểu primitive `boolean` có Java default `false`, vẫn nên khai báo default rõ ràng để metadata và tài liệu plugin dễ hiểu.

### 11.2. Number và file paths

```java
@Parameter(property = "lesson.maxItems", defaultValue = "100")
private int maxItems;

@Parameter(defaultValue = "${project.build.directory}")
private java.io.File outputDir;
```

`defaultValue` không bảo đảm `maxItems` luôn hợp lý. Plugin vẫn cần kiểm tra `maxItems > 0`, output path có thể ghi được và không trỏ ngoài vùng cho phép khi mục tiêu của plugin yêu cầu.

### 11.3. Required phức tạp

Một tham số `List<String>` được đánh dấu required không có nghĩa danh sách luôn chứa ít nhất một phần tử hữu ích. Một Java collection được inject nhưng rỗng vẫn cần kiểm tra nghiệp vụ tùy goal. Kiểm tra null/empty, format từng phần tử và duplicate nếu cần.

### 11.4. Parent POM và pluginManagement

Parent có thể định nghĩa plugin version và default configuration trong `<pluginManagement>`, còn module con sử dụng plugin ở `<plugins>`. Config có thể được kế thừa hoặc được override theo rules Maven. Đừng suy ra child đã có tham số required chỉ từ một file POM con. Dùng `help:effective-pom` để kiểm tra mô hình cuối cùng, sau đó chạy goal với tham số thực tế.

### 11.5. Cấu hình riêng execution

Cùng một goal có thể được cấu hình ở hai executions khác nhau:

```xml
<executions>
    <execution>
        <id>say-first</id>
        <phase>validate</phase>
        <goals><goal>say</goal></goals>
        <configuration>
            <recipient>Alpha</recipient>
        </configuration>
    </execution>
    <execution>
        <id>say-second</id>
        <phase>validate</phase>
        <goals><goal>say</goal></goals>
        <configuration>
            <recipient>Beta</recipient>
        </configuration>
    </execution>
</executions>
```

Đây là **đoạn trong `<plugin>`** (không phải project POM hoàn chỉnh). Mỗi execution có thể có giá trị `recipient` riêng, cùng dùng default `greeting` và readonly expression từ project model. Khi Maven chạy `validate`, hai executions có thể tạo hai thông điệp; thứ tự chính xác còn phụ thuộc vào thứ tự plugin executions/bindings trong effective execution plan.

**Giữ đúng ý nghĩa required:** mỗi invocation của Mojo cần được cấu hình đủ cho yêu cầu của nó, chứ không phải chỉ một lần trên toàn project.

## 12. Vì sao không nên đặt secret vào defaultValue hoặc log

Các ví dụ sau là **anti-pattern**, không nên sao chép vào project thật:

```java
@Parameter(defaultValue = "ACTUAL_PASSWORD_HERE")
private String password;
```

Nếu hardcode credential trong source, nó có thể xuất hiện trong Git, plugin descriptor, artifact JAR, tài liệu help hoặc hệ thống build. **Readonly không giúp che hoặc bảo vệ password**:

```java
@Parameter(defaultValue = "ACTUAL_PASSWORD_HERE", readonly = true)
private String password;
```

Vẫn nguy hiểm vì giá trị nằm trong metadata/binary, người có quyền đọc artifact có thể lấy được.

Đối với plugin cần authentication:
- Dùng Maven settings/servers hoặc cơ chế secret manager được phê duyệt.
- Định rõ scope quyền và tránh hardcode vào POM hoặc source.
- Không in secrets qua `getLog().info`, exception message hoặc debug.
- Không mặc định `-X` hoặc `help:describe` che mọi giá trị nhạy cảm.
- Chỉ chia sẻ phần log đã lược thông tin bí mật.

Thông điệp “tham số bắt buộc” không cho phép plugin ghi toàn bộ đối tượng cấu hình ra log khi thất bại. Báo thiếu **tên tham số** và hướng cấu hình, không in giá trị bí mật.

## 13. Các lỗi phổ biến

**Lỗi 1 — Nghĩ `required=true` luôn buộc phải viết trong `pom.xml`.** Có thể giá trị đến từ user property hoặc default expression. Kiểm tra metadata và mọi nguồn giá trị phù hợp.

**Lỗi 2 — Nghĩ `required=true` kiểm tra chuỗi không rỗng.** Maven kiểm tra cấu hình bắt buộc; nghiệp vụ như `isBlank()`, file tồn tại hay số dương phải được plugin xử lý rõ ràng.

**Lỗi 3 — Nghĩ `defaultValue` là một giá trị không thể thay.** Nếu parameter cho phép và có nguồn giá trị ưu tiên khác, default có thể được ghi đè.

**Lỗi 4 — Nhầm `property` và `defaultValue`.** `property` là tên kênh cấu hình, `defaultValue` là giá trị dự phòng/expression.

**Lỗi 5 — Tin `-D...` luôn thắng cấu hình plugin trong POM.** Không áp dụng quy tắc chung khi XML configuration đã ghi tường minh; thử đúng invocation và inspect effective configuration.

**Lỗi 6 — Nghĩ `readonly=true` là Java `final`.** Đây là metadata về cấu hình người dùng, không phải từ khóa ngôn ngữ.

**Lỗi 7 — Cố ghi `<finalName>` trong `<plugin><configuration>` dù field readonly.** Nên chỉnh `<build><finalName>` nếu parameter lấy từ project model.

**Lỗi 8 — Cho rằng readonly chặn toàn bộ thay đổi từ môi trường.** Nếu expression lấy project data, source đó vẫn có thể thay đổi; readonly không bảo vệ secret hoặc file.

**Lỗi 9 — Đọc `readonly` trong annotation nhưng tìm đúng chữ đó trong descriptor.** Maven descriptor dùng `<editable>false</editable>`.

**Lỗi 10 — Không xem descriptor vì chỉ nhìn Java source.** Plugin Tools phải sinh và đóng gói metadata; class có annotation chưa đủ nếu JAR thiếu `plugin.xml`.

**Lỗi 11 — Gọi `mvn validate` nhưng không thấy goal.** `@Mojo(defaultPhase=VALIDATE)` không tự đăng ký execution; cần binding hoặc gọi goal trực tiếp.

**Lỗi 12 — Test tham số bằng cách gọi goal từ POM khác.** Cấu hình ở execution hoặc plugin khác nhau khiến giá trị nhận được khác; dùng đúng POM/module/phase/CLI.

**Lỗi 13 — Đưa giá trị mật khẩu vào defaultValue.** Descriptor có thể lưu dữ liệu đó; phải dùng cơ chế secret đúng thiết kế.

**Lỗi 14 — Dùng field `int` nhưng truyền chuỗi không chuyển được.** Type conversion có thể thất bại trước `execute()`; metadata và thông báo phải rõ ràng.

**Lỗi 15 — Dùng field `final` cho một parameter Maven vì muốn readonly.** Injection framework có thể không cấu hình như dự kiến; dùng annotation readonly và nguồn model thích hợp.

## 14. Quy trình chẩn đoán khi parameter không như mong đợi

1. **Xác định goal thực sự chạy.** `mvn validate` (phase) khác `mvn plugin:goal` (direct); version plugin và execution ID có thể khác.
2. **Xem Maven/JDK:** chạy `mvn -version`, kiểm tra Java 17+ khi dùng plugin bytecode 17.
3. **Xem POM có hiệu lực:** dùng `help:effective-pom` để xem cấu hình plugin, profiles, inheritance và executions.
4. **Xem mô tả goal:** dùng `help:describe -Dplugin=... -Dgoal=... -Ddetail` để biết Required/Default/User Property.
5. **Xem plugin descriptor nếu cần:** `META-INF/maven/plugin.xml` xác nhận `required`, `editable`, `default-value` và goal implementation.
6. **Liệt kê nguồn giá trị:** plugin-level config, execution config, `-D`, property trong POM, expression model, default value.
7. **Kiểm tra read-only đúng tầng:** nếu parameter lấy từ `project.build.finalName`, hãy sửa build model, không ép cấu hình trực tiếp field readonly.
8. **Đọc root cause của lỗi:** thiếu required, lỗi convert type, Java validation hay lỗi runtime là các trường hợp khác nhau.
9. **Kiểm thử tối thiểu:** chạy lab với default, user property và missing required riêng biệt để thấy hành vi.
10. **Ghi nhận kết quả không lộ secret:** chỉ cung cấp tên tham số, nguồn giá trị (không phải giá trị bí mật), plugin/version và thông điệp lỗi đã kiểm duyệt.

Dùng Maven Help Plugin để kiểm tra project:

```bash
mvn -f demo-consumer/pom.xml help:effective-pom
```

Khi debug, hãy nhớ effective POM không phải toàn bộ dữ liệu cuối của plugin parameter injection. Muốn biết trường thật đã nhận gì, trong plugin của chính bạn có thể thêm test hoặc logging **các giá trị không nhạy cảm**, theo quy định bảo mật.

## 15. Bài tập tự kiểm tra

**Câu 1.** `@Parameter(required=true)` có luôn yêu cầu `<configuration>` trong POM không?

**Đáp án:** Không. Parameter có thể nhận từ property, inheritance, default expression hoặc nguồn cấu hình khác. Required chỉ nói về giá trị phải có khi Maven cấu hình goal.

**Câu 2.** `@Parameter(defaultValue="Hello")` có ý nghĩa gì?

**Đáp án:** Khi không có nguồn cấu hình phù hợp khác, Maven inject giá trị dự phòng `Hello`. Nó không có nghĩa người dùng không thể thay đổi.

**Câu 3.** `@Parameter(property="lesson.greeting", defaultValue="Hello")` khác `@Parameter(defaultValue="lesson.greeting")` ở đâu?

**Đáp án:** Trường hợp đầu có property channel `lesson.greeting` và default literal `Hello`. Trường hợp sau mặc định là chuỗi literal `lesson.greeting`, không tự suy ra đó là tên property để đọc.

**Câu 4.** `@Parameter(readonly=true)` có làm field Java thành `final` không?

**Đáp án:** Không. Nó giới hạn cấu hình trực tiếp trong plugin configuration, không phải cú pháp Java hoặc bảo vệ filesystem.

**Câu 5.** Nếu field readonly lấy `${project.build.finalName}`, người dùng nên chỉnh ở đâu?

**Đáp án:** Chỉnh `<build><finalName>...` ở POM project cho đúng ngữ nghĩa, thay vì cố đặt tham số readonly trong `<plugin><configuration>`.

**Câu 6.** Plugin descriptor ghi field readonly là `readonly=true` hay `editable=false`?

**Đáp án:** Với descriptor Maven 3, thuộc tính tương ứng là `<editable>false</editable>`.

**Câu 7.** Một field `required=true, defaultValue="x"` có nhất thiết thất bại khi người dùng bỏ qua trong POM không?

**Đáp án:** Không. Default có thể cung cấp giá trị, nên cấu hình required đã được thỏa; vẫn cần kiểm tra yêu cầu nghiệp vụ.

**Câu 8.** Người dùng truyền một số âm vào `maxItems` có `required=true`. Required có kiểm tra số dương không?

**Đáp án:** Không. Required không thay thế validation nội dung; plugin cần kiểm tra `maxItems > 0` nếu đó là hợp đồng.

**Câu 9.** Trong lab, khi chạy `mvn validate` với consumer POM ban đầu, hai message là gì?

**Đáp án:** `Hello, Maven!` và `Project finalName: consumer-release`.

**Câu 10.** Thêm `-Dlesson.greeting=Welcome` mà không cấu hình `<greeting>` tường minh, điều gì thay đổi?

**Đáp án:** Greeting đổi từ `Hello` thành `Welcome`; recipient vẫn `Maven` và finalName vẫn từ project model.

**Câu 11.** Nếu bỏ recipient và không truyền `-Dlesson.recipient`, goal `say` sẽ ra sao?

**Đáp án:** Nó có thể bị Maven từ chối khi cấu hình Mojo vì thiếu required parameter. Không nên phụ thuộc vào một câu stderr cố định giữa các phiên bản.

**Câu 12.** `help:describe` có thể hỗ trợ điều tra gì?

**Đáp án:** Goal name, parameter type, Required, Default, User Property và thông tin descriptor được trình bày theo phiên bản Help Plugin.

**Câu 13.** Tại sao không nên đặt password vào `defaultValue` kể cả với `readonly=true`?

**Đáp án:** Readonly không phải secret protection; default có thể nằm trong source, descriptor/JAR hoặc log, gây lộ thông tin.

**Câu 14.** Hai executions của cùng goal dùng hai `<recipient>` khác nhau. Required được kiểm tra mấy lần?

**Đáp án:** Mỗi invocation của Mojo cần có cấu hình hợp lệ; không coi việc một execution có dữ liệu là tất cả executions đều được đáp ứng.

## Tài liệu chính thức tham khảo

- [Maven Plugin Tools 3.16.0 – `@Parameter` API](https://maven.apache.org/components/plugin-tools/maven-plugin-annotations/apidocs/org/apache/maven/plugins/annotations/Parameter.html): `required`, `readonly`, `defaultValue`, `property` và ý nghĩa chính thức.
- [Maven Plugin Tools – Java Annotations](https://maven.apache.org/plugin-tools/maven-plugin-tools-annotations/index.html): các cách mô tả parameter/Mojo và injection từ Maven.
- [Maven Plugin API 3.9.9 – Plugin Descriptor](https://maven.apache.org/ref/3.9.9/maven-plugin-api/plugin.html): `plugin.xml`, `<required>`, `<editable>` và `default-value`.
- [Maven Plugin Plugin – `plugin:descriptor`](https://maven.apache.org/plugin-tools/maven-plugin-plugin/descriptor-mojo.html): goal sinh plugin descriptor.
- [Maven Plugin Plugin – Usage](https://maven.apache.org/plugin-tools/maven-plugin-plugin/usage.html): file `target/classes/META-INF/maven/plugin.xml` và đóng gói.
- [Maven Help Plugin – `help:describe`](https://maven.apache.org/plugins/maven-help-plugin/describe-mojo.html): hiển thị thông tin goal, parameter và `-Ddetail`.
- [Apache Maven – Guide to Developing Java Plugins](https://maven.apache.org/guides/plugin/guide-java-plugin-development): cách tạo Maven plugin, Mojo và sử dụng metadata.
- [Apache Maven – Configuring Plugins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html): `<plugins>`, `<executions>`, `<configuration>` và inheritance.
- [Apache Maven – Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): phases, goals và bindings khi thực thi.
