# StringTrimmerEditor và chuyển chuỗi rỗng thành null trong Spring Framework

Trong ứng dụng web, người dùng thường gửi các giá trị như `"  Lan  "`, `""` hoặc `"   "`. Dù trường nhập liệu nhìn có vẻ trống, dữ liệu nhận được vẫn có thể là một đối tượng `String` không rỗng, chỉ chứa khoảng trắng. **`StringTrimmerEditor`** của Spring giúp chuẩn hóa những giá trị chuỗi đó khi **property binding**: cắt khoảng trắng ở hai đầu và, nếu cấu hình, biến kết quả rỗng thành **`null`**.

Điểm cốt lõi là hai hành vi tách biệt:

1. **Trim**: `"  Lan  "` trở thành `"Lan"`.
2. **Empty-as-null**: khi chuỗi đã xử lý thành `""`, chuyển thành `null` nếu chọn `emptyAsNull=true`; nếu chọn `false` thì giữ `""`.

`StringTrimmerEditor` nằm trong nhóm **PropertyEditor**, không phải annotation validation, không tự được kích hoạt bởi mọi HTTP request, và **không được Spring đăng ký mặc định cho mọi chuỗi**. Bài này giải thích API, cách đăng ký vào `DataBinder`/`WebDataBinder`, khác biệt giữa chuỗi trống và `null`, tác động đến Bean Validation, ví dụ Java 17 chạy được, cùng các lỗi sử dụng thực tế.

## 1. Vì sao cần phân biệt rỗng, khoảng trắng và null?

Java có ba giá trị rất dễ bị đánh đồng:

| Giá trị | `value == null` | `value.isEmpty()` | `value.isBlank()` với Java 17 |
| --- | --- | --- | --- |
| `null` | `true` | Không gọi được; sẽ `NullPointerException` | Không gọi được |
| `""` | `false` | `true` | `true` |
| `"   "` | `false` | `false` | `true` |
| `"  Lan  "` | `false` | `false` | `false` |

Đối với một property `middleName` tùy chọn, nhiều ứng dụng muốn coi `""` và `"   "` đều là **không cung cấp dữ liệu**, biểu diễn bằng `null` trong DTO. Nhờ đó, logic phía sau có thể kiểm tra `middleName == null` thay vì phải tự xử lý nhiều biến thể khoảng trắng.

Ngược lại, với dữ liệu đầu vào cần giữ nguyên byte/ký tự, như mật khẩu, chữ ký, nội dung tài liệu hoặc đoạn text nhiều dòng, việc tự động trim có thể **làm thay đổi ý nghĩa dữ liệu**. Vì vậy không thể áp dụng một cách mù quáng trên mọi `String` trong toàn ứng dụng.

**Quy tắc nền tảng:** `null` là **không có giá trị tham chiếu**; `""` là **có đối tượng String với độ dài bằng 0**; `"   "` là chuỗi có ký tự nhưng chỉ toàn khoảng trắng theo cách nhìn thông thường. Việc có nên nhập ba trường hợp làm một là **quyết định của hợp đồng đầu vào**.

## 2. StringTrimmerEditor là gì?

Class đầy đủ:

```java
org.springframework.beans.propertyeditors.StringTrimmerEditor
```

Nó kế thừa `java.beans.PropertyEditorSupport`, thực hiện cơ chế `PropertyEditor` của JavaBeans. Spring có thể đăng ký editor này vào một binder để chuyển đổi **dữ liệu dạng chuỗi thành giá trị property kiểu `String`** trước khi gọi setter tương ứng.

Hai constructor chính:

```java
new StringTrimmerEditor(true);
new StringTrimmerEditor(false);
new StringTrimmerEditor("\r\n\f", true);
```

| Constructor | Ý nghĩa |
| --- | --- |
| `StringTrimmerEditor(true)` | Trim đầu/cuối; nếu kết quả rỗng thì đặt value là `null` |
| `StringTrimmerEditor(false)` | Trim đầu/cuối nhưng giữ kết quả rỗng là `""` |
| `StringTrimmerEditor(charsToDelete, emptyAsNull)` | Trim, sau đó xóa các ký tự được liệt kê trong `charsToDelete`, rồi xét điều kiện rỗng để đổi thành `null` nếu bật cờ |

Không có ý nghĩa “trim được bật hay tắt” trong đối số boolean: **boolean này chỉ điều khiển chuyển chuỗi rỗng thành `null`**. Cả `true` và `false` đều thực hiện trim.

### Cách xử lý trong setAsText

Có thể hiểu quy tắc xử lý của editor bằng thuật toán giản lược:

```java
void conceptualSetAsText(String text) {
    if (text == null) {
        setValue(null);
        return;
    }

    String value = text.trim();

    if (charsToDelete != null) {
        value = StringUtils.deleteAny(value, charsToDelete);
    }

    setValue(emptyAsNull && value.isEmpty() ? null : value);
}
```

Đây là **pseudo-code minh họa**, không phải phương thức có thể copy vào class độc lập: `charsToDelete`, `emptyAsNull` và `setValue` là các phần của triển khai editor; `StringUtils` là tiện ích của Spring. Điều quan trọng là **thứ tự: trim → xóa các ký tự tùy chọn → chuyển empty thành null**.

Một input ban đầu là `null` vẫn là `null` kể cả khi `emptyAsNull=false`. Cờ `false` **không chuyển null thành chuỗi rỗng**.

### Getter/setter của PropertyEditor

- `setAsText(String)`: nhận text và chuyển thành giá trị được editor lưu.
- `getValue()`: lấy giá trị đã được chuyển; có thể là `String` hoặc `null`.
- `getAsText()`: thể hiện giá trị hiện tại dưới dạng text; với `StringTrimmerEditor`, khi giá trị bên trong là `null`, kết quả text là `""`.

Do `getAsText()` có thể biểu diễn `null` thành `""`, muốn kiểm tra việc chuyển sang `null` thì xem **`getValue()` hoặc property thực tế trên target**, không chỉ dựa vào text hiển thị.

## 3. Bảng hành vi: emptyAsNull true so với false

Giả sử không truyền `charsToDelete` bổ sung và dùng cơ chế trim của editor.

| Đầu vào | `new StringTrimmerEditor(true)` | `new StringTrimmerEditor(false)` |
| --- | --- | --- |
| `null` | `null` | `null` |
| `""` | `null` | `""` |
| `"   "` | `null` | `""` |
| `" \t "` | `null` | `""` |
| `"  Lan  "` | `"Lan"` | `"Lan"` |
| `" A  B "` | `"A  B"` | `"A  B"` |
| `"null"` (bốn ký tự) | `"null"` | `"null"` |
| `"  42  "` | `"42"` | `"42"` |

Ba điểm cần nhớ:

1. **Không xóa khoảng trắng ở giữa chuỗi**: `" A  B "` trở thành `"A  B"`. Đây là một thao tác trim, không phải chức năng nén mọi khoảng trắng thành một.
2. Chuỗi có nội dung `"null"` vẫn là **bốn chữ cái**, không phải giá trị `null` của Java. Editor không diễn giải nội dung chữ theo nghĩa đặc biệt.
3. Editor dùng cơ chế `String.trim()` của Java: không nên giả định nó xóa **mọi** loại Unicode whitespace, ví dụ non-breaking space (`U+00A0`). `String.isBlank()` và `String.strip()` của Java có quy tắc khác; đừng đồng nhất chúng với `String.trim()`.

Các bảng trên mô tả thao tác với chuỗi được đưa **qua editor**. Nếu bạn gọi setter của DTO trực tiếp:

```java
form.setName("   ");
```

thì không có `StringTrimmerEditor` nào tự động xuất hiện chỉ vì dự án sử dụng Spring. Normalization là hành vi của **đường chuyển đổi/binding đã cấu hình**, không phải một đặc tính của mọi setter.

## 4. Tùy chọn xóa ký tự: charsToDelete

Constructor hai tham số:

```java
StringTrimmerEditor editor =
        new StringTrimmerEditor("\r\n\f", true);
```

Ký tự trong chuỗi `charsToDelete` là **một tập các ký tự cần xóa ở bất kỳ vị trí nào sau khi trim**, không phải một regex và cũng không chỉ xóa ở đầu/cuối.

Ví dụ:

```java
editor.setAsText("  AB\nCD  ");
System.out.println(editor.getValue()); // "ABCD"
```

Vì editor xóa ký tự newline ở giữa, hai dòng bị nối lại thành `ABCD`. Khi input chỉ còn các ký tự thuộc danh sách xóa và/hoặc các ký tự bị trim, kết quả cuối có thể thành `""` và được chuyển sang `null` nếu `emptyAsNull=true`.

**Cẩn thận:** thêm dấu cách thường (`" "`) vào `charsToDelete` có thể xóa **cả dấu cách bên trong**, dẫn đến `"Ho Chi Minh"` thành `"HoChiMinh"`. Điều này khác trim thông thường và dễ làm hỏng dữ liệu tên, địa chỉ, nội dung tự do. Việc xóa newline có thể không phù hợp với textarea và comment nhiều dòng; hãy đặt chính sách phù hợp từng trường.

## 5. Cách đăng ký với DataBinder

`DataBinder` thuộc `org.springframework.validation`. Nó không áp dụng `StringTrimmerEditor` một cách tự động; người viết code cần đăng ký editor qua `registerCustomEditor(...)`.

### Áp dụng cho tất cả property kiểu String

```java
DataBinder binder = new DataBinder(form, "form");
binder.registerCustomEditor(
        String.class, new StringTrimmerEditor(true));
```

Ở đây:

- `String.class` là kiểu property cần chuyển đổi.
- `new StringTrimmerEditor(true)` là editor chuẩn hóa.
- Cấu hình này áp dụng cho các property kiểu `String` được binder **thực sự bind** thông qua cơ chế phù hợp.
- Đăng ký không đồng nghĩa tự sửa tất cả giá trị đang tồn tại trên `form`. Không có lần bind/convert phù hợp thì setter không được gọi chỉ vì editor đã đăng ký.

Sau đó `binder.bind(MutablePropertyValues)` có thể chuyển text đầu vào thành `null` hoặc chuỗi đã trim rồi mới ghi vào bean.

### Chỉ áp dụng cho một property cụ thể

`DataBinder` cũng có overload với tên field:

```java
binder.registerCustomEditor(
        String.class,
        "displayName",
        new StringTrimmerEditor(true));
```

Cách này hữu ích khi chỉ trường `displayName` được phép trim, còn `rawMessage` hoặc `secretValue` phải giữ nguyên dữ liệu.

Nếu property nằm trong object con, có thể truyền path như `"contact.displayName"` khi binder target là object cha có property đó. Không viết path theo suy đoán: target của binder quyết định đường dẫn bắt đầu từ đâu.

**Một property path không nên đăng ký nhiều editor xung đột**. Đặc biệt khi có editor cho loại collection và editor cho phần tử trong cùng một path, cần xem quy tắc cụ thể của `PropertyEditorRegistry`. Với bài toán trim chuỗi thông thường, một editor String kiểu-wide hoặc một editor String field-specific rõ ràng là đủ.

### Khi dùng editor theo kiểu String.class có gì đáng lưu ý?

Đây là cấu hình rộng: tên, mô tả, ghi chú, nội dung người dùng đều có thể bị trim nếu được bind qua cùng binder và khớp kiểu. Nếu ứng dụng cần giữ nguyên xuống dòng, khoảng trắng hay bí mật người dùng, cân nhắc đăng ký theo field thay vì áp dụng cho toàn bộ String.

`StringTrimmerEditor` là một **PropertyEditor có trạng thái** (giá trị lưu trong instance). Thực hành tốt là tạo editor cho binder/request phù hợp như trong `@InitBinder`, không tự chia sẻ một instance mutable toàn cục giữa các request và thread.

## 6. Ví dụ Java 17 chạy được: trim, đổi null và binding

Ví dụ này sử dụng `DataBinder` trực tiếp, **không cần Spring Boot hay HTTP server**. Ta sẽ kiểm tra tác dụng trên editor, cách áp dụng cho toàn bộ `String`, sự khác nhau khi chỉ áp dụng cho một field, và việc field **không xuất hiện trong đầu vào** được giữ nguyên.

### 6.1. Cấu trúc dự án

```text
string-trimmer-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/StringTrimmerDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'string-trimmer-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
}

application {
    mainClass = 'example.StringTrimmerDemo'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

Dùng JDK 17+ và Gradle có khả năng chạy trên JDK đó, với Maven Central cho lần tải dependency đầu tiên. `spring-context` mang theo các module Spring cần cho `DataBinder` và `StringTrimmerEditor`; ví dụ không phụ thuộc vào Jakarta Validation.

### 6.2. Mã Java đầy đủ

**`src/main/java/example/StringTrimmerDemo.java`**

```java
package example;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.beans.propertyeditors.StringTrimmerEditor;
import org.springframework.validation.DataBinder;

public class StringTrimmerDemo {

    public static class ContactForm {
        private String name;
        private String nickname;
        private String note;
        private String missing = "original";

        public ContactForm() {
        }

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public String getNickname() {
            return nickname;
        }

        public void setNickname(String nickname) {
            this.nickname = nickname;
        }

        public String getNote() {
            return note;
        }

        public void setNote(String note) {
            this.note = note;
        }

        public String getMissing() {
            return missing;
        }

        public void setMissing(String missing) {
            this.missing = missing;
        }
    }

    private static String show(String value) {
        return value == null ? "<null>" : "[" + value + "]";
    }

    public static void main(String[] args) {
        StringTrimmerEditor direct = new StringTrimmerEditor(true);
        direct.setAsText("  Lan  ");
        System.out.println("direct=" + show((String) direct.getValue()));

        direct.setAsText(" \t ");
        System.out.println(
                "emptyAsNull=" + show((String) direct.getValue()));

        StringTrimmerEditor keepEmpty = new StringTrimmerEditor(false);
        keepEmpty.setAsText(" \t ");
        System.out.println(
                "keepEmpty=" + show((String) keepEmpty.getValue()));

        StringTrimmerEditor deleteLineBreaks =
                new StringTrimmerEditor("\r\n", true);
        deleteLineBreaks.setAsText(" A\nB ");
        System.out.println(
                "deleteLineBreaks="
                        + show((String) deleteLineBreaks.getValue()));

        direct.setAsText(null);
        System.out.println(
                "nullInput=" + show((String) direct.getValue()));
        System.out.println("nullAsText=[" + direct.getAsText() + "]");

        ContactForm form = new ContactForm();
        DataBinder binder = new DataBinder(form, "contactForm");
        binder.registerCustomEditor(
                String.class, new StringTrimmerEditor(true));

        MutablePropertyValues values = new MutablePropertyValues();
        values.add("name", "  Lan Anh  ");
        values.add("nickname", "  \t  ");
        values.add("note", "  Two  spaces  ");

        binder.bind(values);

        System.out.println("bindName=" + show(form.getName()));
        System.out.println("bindNickname=" + show(form.getNickname()));
        System.out.println("bindNote=" + show(form.getNote()));
        System.out.println("bindMissing=" + show(form.getMissing()));
        System.out.println(
                "errors=" + binder.getBindingResult().getErrorCount());

        ContactForm pathOnly = new ContactForm();
        DataBinder pathBinder = new DataBinder(pathOnly, "contactForm");
        pathBinder.registerCustomEditor(
                String.class, "name", new StringTrimmerEditor(true));

        MutablePropertyValues pathValues = new MutablePropertyValues();
        pathValues.add("name", "  Mai  ");
        pathValues.add("nickname", "   ");

        pathBinder.bind(pathValues);

        System.out.println("onlyName=" + show(pathOnly.getName()));
        System.out.println(
                "onlyNickname=" + show(pathOnly.getNickname()));
    }
}
```

### 6.3. Chạy và stdout

Trong thư mục `string-trimmer-demo`:

```bash
gradle -q run
```

Nếu đã có Gradle wrapper thì dùng `./gradlew -q run` trên Linux/macOS hoặc `gradlew.bat -q run` trên Windows.

**Stdout mong đợi:**

```text
direct=[Lan]
emptyAsNull=<null>
keepEmpty=[]
deleteLineBreaks=[AB]
nullInput=<null>
nullAsText=[]
bindName=[Lan Anh]
bindNickname=<null>
bindNote=[Two  spaces]
bindMissing=[original]
errors=0
onlyName=[Mai]
onlyNickname=[   ]
```

Giải thích:

1. `direct` cho thấy trim chuỗi có nội dung: `"  Lan  "` thành `"Lan"`.
2. `emptyAsNull`: sau khi trim `" \t "` thành rỗng, editor tạo **`null`**.
3. `keepEmpty`: cùng đầu vào nhưng boolean `false`, nên value là `""`; hàm `show` biểu diễn bằng `[]`, khác `<null>`.
4. `deleteLineBreaks` xóa newline ở giữa `A` và `B` nhờ `charsToDelete="\r\n"`, thành `"AB"`.
5. `nullInput` giữ `null`. Nhưng `getAsText()` hiển thị chuỗi rỗng cho giá trị `null`, nên `nullAsText=[]`; đừng nhầm text trình bày với value lưu.
6. Khi đăng ký toàn bộ kiểu `String.class`, `name` được trim; `nickname` chỉ chứa khoảng trắng thành `null`; `note` giữ nguyên **hai dấu cách ở giữa**.
7. `missing` không nằm trong `MutablePropertyValues`, vì vậy không bị tự chỉnh sửa và giữ giá trị ban đầu `"original"`.
8. `errors=0`: ví dụ không có conversion error và không đăng ký constraint validator. Editor **không tự tạo lỗi validation** chỉ vì nó chuyển chuỗi rỗng thành `null`.
9. Với overload theo property `"name"`, chỉ `name` qua trimmer; `nickname` không có editor riêng nên vẫn là chuỗi ba dấu cách. Kết quả `onlyNickname=[   ]` khác `null`.

Mỗi binder ở ví dụ chỉ dùng cho một luồng bind và có editor riêng. Dù editor có thể gọi `setAsText` trực tiếp nhiều lần trong test tuần tự, không nên sử dụng cùng một instance giữa nhiều luồng xử lý song song.

## 7. Đăng ký trong Spring MVC bằng @InitBinder

Trong Spring MVC (Servlet stack), `WebDataBinder` mở rộng `DataBinder`. Phương thức `@InitBinder` giúp đăng ký editor cho binder đang phục vụ một model attribute.

Ví dụ **đoạn tích hợp** trong một controller:

```java
import org.springframework.beans.propertyeditors.StringTrimmerEditor;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;

@InitBinder("contactForm")
void initContactBinder(WebDataBinder binder) {
    binder.registerCustomEditor(
            String.class, new StringTrimmerEditor(true));
}
```

Đoạn trên phải được đặt **bên trong class controller Spring MVC hoặc controller advice phù hợp**; đây không phải Java SE program độc lập. Tên `"contactForm"` cần tương ứng với model attribute thực tế:

```java
@PostMapping("/contacts")
public String submit(
        @Valid @ModelAttribute("contactForm") ContactForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return "contacts/form";
    }
    return "contacts/result";
}
```

Đoạn `@PostMapping` cũng là **mã tích hợp**, cần các imports Spring MVC/Jakarta Validation, lớp `ContactForm`, view templates và cấu hình ứng dụng tương ứng. Các ví dụ đó chỉ minh họa **đúng vị trí** mà editor tham gia; ví dụ chạy độc lập đầy đủ ở phần 6.

Luồng xử lý điển hình của một form URL-encoded:

```text
POST /contacts
Content-Type: application/x-www-form-urlencoded

name=++Lan++&nickname=+++
            |
            v
Spring MVC chuẩn bị WebDataBinder cho "contactForm"
            |
            v
@InitBinder đăng ký StringTrimmerEditor(true)
            |
            v
Đọc request parameters → chuyển đổi và property binding
            |
            +-- name: "  Lan  " → "Lan"
            +-- nickname: "   " → null
            |
            v
Chạy validation nếu được kích hoạt (@Valid / @Validated)
            |
            v
Controller đọc ContactForm và BindingResult
```

Lưu ý `+` trong `application/x-www-form-urlencoded` thường được giải mã thành dấu cách. Luồng trên giả định việc binder thực sự nhận các field và chúng không bị loại khỏi tập được phép bind. `@InitBinder` **cấu hình** editor, không tự gọi `binder.bind(...)` hay `binder.validate()` chỉ vì annotation xuất hiện.

### Controller-local, model-attribute-specific hay toàn cục?

- `@InitBinder("contactForm")` trong controller giới hạn cấu hình theo tên model attribute tương ứng.
- `@InitBinder` không chỉ định tên trong controller có phạm vi áp dụng rộng hơn đối với các binder thuộc controller đó.
- `@InitBinder` trong `@ControllerAdvice` có thể áp dụng cho một tập controller được advice quản lý. Nếu chuẩn hóa mọi chuỗi ở cấp rộng, phải kiểm tra các trường như password, rich text và textarea.

Đây là lý do nên chọn phạm vi đăng ký **hẹp nhất phù hợp** với yêu cầu dữ liệu.

## 8. Khác biệt giữa field vắng mặt và field có chuỗi trống

Một form có ba kịch bản khác nhau:

| Tình huống | Dữ liệu request | Kết quả có thể xảy ra với StringTrimmerEditor(true) |
| --- | --- | --- |
| Trường hiện diện nhưng không nhập gì | `name=` | Property được bind thành `null` |
| Trường chỉ chứa khoảng trắng | `name=+++` (URL-encoded) | Sau decode + trim, thành `null` |
| Trường không xuất hiện trong request | Không có key `name` | Editor thường không chạy cho field này; giá trị hiện có trên target được giữ nguyên |

Điều này đặc biệt quan trọng khi update một object **đã có dữ liệu**. `StringTrimmerEditor` không tự đặt mọi property bị thiếu thành `null`. Nếu muốn thao tác PATCH có nghĩa “xóa giá trị”, hãy xác định rõ hợp đồng giữa **field bị bỏ qua** và **field được gửi là chuỗi trống**. Với các model attribute được tái sử dụng, giá trị trước khi bind và chính sách setter đều ảnh hưởng đến kết quả.

`"null"` (bốn chữ cái) không phải `null`; editor chỉ chuyển **chuỗi sau chuẩn hóa có độ dài bằng 0**. Tương tự, chuỗi `"0"` hoặc `"false"` vẫn có nội dung — nó không bị chuyển thành null chỉ vì biểu diễn một giá trị thường được xem là giả.

## 9. Ảnh hưởng đến Jakarta Bean Validation

`StringTrimmerEditor` thực hiện **normalization/conversion**. Các annotation như `@NotNull`, `@NotEmpty` và `@NotBlank` thực hiện **validation**. Thứ tự điển hình với `@ModelAttribute` là binding rồi mới validate, nên editor có thể thay đổi giá trị đầu vào mà các constraint nhìn thấy.

Giả sử đầu vào là `"   "` và kiểu property là `String`:

| Constraint | Nếu không trim | Nếu StringTrimmerEditor(true) được áp dụng |
| --- | --- | --- |
| `@NotNull` | Thường qua, vì value là String không null | Không qua, vì value thành `null` |
| `@NotEmpty` | Thường qua, vì có ba ký tự | Không qua, vì value thành `null` |
| `@NotBlank` | Không qua, vì chỉ có khoảng trắng | Không qua, vì value thành `null` |
| `@Size(min=1)` | Thường qua vì độ dài 3 | `null` thường được `@Size` coi là hợp lệ; cần thêm `@NotNull` nếu bắt buộc |
| `@Pattern(...)` | Tùy regex cụ thể | `null` thường không bị `@Pattern` từ chối; kết hợp `@NotNull` nếu cần |

Bảng này giả định Jakarta Bean Validation provider đã được cấu hình và constraint thực sự được chạy. Không nên suy ra trường nào cũng có `@Valid` hoặc mọi validation đều tự kích hoạt bởi việc đăng ký editor.

### Chọn constraint theo ý định

- Dùng `@NotBlank` cho text bắt buộc không được là khoảng trắng.
- Dùng `@NotNull` khi sự hiện diện của giá trị là điều kiện bắt buộc.
- Dùng `@NotEmpty` khi giá trị không được null hoặc rỗng; với String toàn khoảng trắng, cần hiểu liệu editor đã chuẩn hóa trước hay chưa.
- Dùng `@Size` cho giới hạn độ dài; tự nó không bảo đảm property khác null.

Ví dụ DTO tích hợp:

```java
public class ContactForm {
    @NotBlank
    private String name;

    private String nickname;

    // Getter, setter và constructor theo cơ chế binding đã chọn.
}
```

Đây là đoạn **minh họa**, cần import `jakarta.validation.constraints.NotBlank` và các accessor thực tế. Nếu `nickname` chỉ chứa khoảng trắng và editor true được áp dụng, nó thành `null`, còn `name` bị `@NotBlank` từ chối khi trống. Bản thân editor không quyết định trả HTTP 400 hay nội dung thông báo; controller và validation/error handling mới quyết định.

**Tránh lệ thuộc ngầm vào normalization.** Một validation rule được dùng cả ở Spring MVC, batch import và asynchronous consumer có thể nhận dữ liệu không đi qua `StringTrimmerEditor`. Nếu hệ thống bắt buộc lưu dữ liệu ở dạng chuẩn, hãy thiết kế chính sách normalization nhất quán tại các entrypoint đáng tin cậy, chứ không chỉ một controller.

## 10. Điều gì không được StringTrimmerEditor xử lý?

Editor này có phạm vi rất cụ thể:

1. **Không phải bộ lọc bảo mật**: không sanitize HTML, không ngăn SQL injection, không escape đầu ra, không xác minh quyền truy cập. Query parameterization, output encoding và access control vẫn là những vấn đề riêng.
2. **Không kiểm tra định dạng email, số điện thoại hay URL**: `"bad-email"` vẫn là chuỗi có nội dung sau trim.
3. **Không mặc định xóa khoảng trắng ở giữa**: `"An  Bình"` vẫn có hai dấu cách giữa tên.
4. **Không mặc định chuẩn hóa mọi Unicode whitespace**: cách trim của nó dựa trên `String.trim()`, không đồng nghĩa Unicode normalization.
5. **Không tự xử lý dữ liệu ngoài binder**: object được dựng thủ công, setter được gọi trực tiếp hoặc batch job không đi qua editor sẽ không chịu tác dụng.
6. **Không đảm bảo áp dụng cho `@RequestBody` JSON**: Spring MVC thường dùng `HttpMessageConverter`/Jackson để deserialize JSON. Editor của `WebDataBinder` dành cho property binding không phải cơ chế Jackson mặc định.
7. **Không phải giải pháp cho lỗi converter kiểu khác**: input `age=abc` đối với `Integer age` không tự được chữa bằng editor đăng ký cho `String.class`.
8. **Không phải tương đương với `StringUtils.hasText` hoặc `String.isBlank`**: các phương thức này kiểm tra text, còn editor **biến đổi** giá trị khi chuyển đổi.
9. **Không quyết định cách lưu database**: JPA, JDBC và serialization làm việc với dữ liệu nhận được; editor không tự thay đổi mọi bản ghi cũ.

Với `@RequestParam`, `@PathVariable` và các resolver khác, đường chuyển đổi có thể dùng các hạ tầng binder/conversion theo ngữ cảnh; đừng khẳng định một `@InitBinder` sẽ trim mọi loại đối số một cách giống hệt `@ModelAttribute`. Kiểm thử hành vi thật của endpoint tương ứng.

## 11. Những lỗi sử dụng StringTrimmerEditor thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| Đã tạo `new StringTrimmerEditor(true)` nhưng field vẫn giữ dấu cách | Chưa `registerCustomEditor` vào binder đang bind field | Đăng ký đúng binder, đúng model attribute |
| Chuỗi trắng vẫn là `""` thay vì `null` | Dùng `StringTrimmerEditor(false)` | Dùng `true` nếu hợp đồng đầu vào coi trống là null |
| Trường không gửi trong request không thành null | Editor không tự duyệt mọi property không được bind | Phân biệt missing với blank trong logic update |
| Chữ trong chuỗi mất dấu cách nội bộ | `charsToDelete` chứa cả dấu cách | Không đưa dấu cách vào danh sách xóa nếu cần giữ nội dung |
| Text nhiều dòng mất newline | `charsToDelete` có `\r\n` | Chỉ dùng cấu hình xóa newline khi thực sự phù hợp |
| Password bị trim và không còn đúng chuỗi gốc | Đăng ký toàn bộ String không xét tính chất field | Áp dụng theo field hoặc tách form có quy tắc khác |
| Tên hoặc email sau trim không còn nguyên raw input | Normalization là biến đổi mất thông tin | Giữ raw value riêng nếu nghiệp vụ/audit yêu cầu |
| `@NotNull` bỗng từ qua thành không qua | Editor true đổi blank String thành null trước validation | Điều chỉnh contract và test constraint tương ứng |
| `@Size(min=1)` không bắt blank sau khi editor chạy | Giá trị null có thể được `@Size` chấp nhận | Kết hợp `@NotNull` hoặc dùng `@NotBlank` |
| JSON `@RequestBody` vẫn giữ khoảng trắng | Dữ liệu deserialize qua Jackson, không phải property editor của form | Dùng chiến lược normalization dành riêng cho JSON/DTO |
| Một test pass, nhiều request đồng thời lỗi kỳ lạ | Chia sẻ instance `PropertyEditor` có trạng thái giữa các thread | Khởi tạo editor trong phạm vi binder thích hợp |
| NBSP hoặc một số Unicode spaces không biến mất | Cơ chế `trim()` không xóa tất cả code point trắng | Xác định chính sách Unicode và dùng normalization khác nếu cần |

### Cẩn thận với "xóa mọi khoảng trắng"

Tránh biến:

```java
new StringTrimmerEditor(" ", true)
```

thành một cách xử lý mặc định. Nó có thể xóa **toàn bộ ký tự dấu cách thông thường** sau trim, kể cả bên trong giá trị có nghĩa. Với `"Ho Chi Minh"`, kết quả có thể thành `"HoChiMinh"`, không phải `"Ho Chi Minh"`. Muốn trim đầu/cuối và chuyển blank thành null, chỉ cần:

```java
new StringTrimmerEditor(true)
```

### Cẩn thận với vòng đời editor

`PropertyEditorSupport` lưu trạng thái value. Một instance được dùng tuần tự trong demo là hợp lệ để quan sát `setAsText/getValue`. Nhưng nếu đăng ký một singleton editor mutable cho nhiều binder chạy song song, có nguy cơ ảnh hưởng chéo giữa các request. Trên hệ thống web, tạo editor trong `@InitBinder` và không chia sẻ đối tượng editor mutable giữa các luồng.

## 12. Kiểm tra và gỡ lỗi theo từng bước

Khi editor không cho kết quả như mong đợi, dùng checklist:

1. **Xác định input thực tế**: key có xuất hiện không? Value là `""`, `"   "`, `null` hay thiếu hoàn toàn?
2. **Xác định nguồn dữ liệu**: form URL-encoded / query parameter / JSON body / object tạo thủ công?
3. **Xác định binder**: có phải binder của đúng model attribute không, `@InitBinder` đã được gọi chưa?
4. **Xem đăng ký editor**: `registerCustomEditor(String.class, ...)` hay overload với field path? Có một formatter/converter/editor khác cạnh tranh?
5. **Kiểm tra trình tự**: đã gọi `bind(...)` trước khi đọc giá trị chưa? Đã kích hoạt validation nếu cần chưa?
6. **Quan sát target**: dùng getter kiểm tra `== null` và độ dài String, đừng chỉ nhìn text render.
7. **So sánh true và false**: với một blank input, `true` cho `null`, `false` cho `""`.
8. **Kiểm tra khoảng trắng đặc biệt**: nếu dữ liệu có Unicode whitespace hoặc line breaks, xác định loại ký tự; `trim()` không giải quyết mọi trường hợp.
9. **Đối chiếu validation**: `@NotNull`, `@NotEmpty`, `@NotBlank` và `@Size` cho kết quả khác nhau; test cả blank và missing.
10. **Xác minh an toàn dữ liệu**: thử text nhiều dòng, password và các trường cần giữ nguyên ký tự trước khi đăng ký kiểu-wide.

Có thể viết unit test theo bảng ca kiểm thử sau:

| Trường hợp test | Input | Giá trị mong đợi với editor true |
| --- | --- | --- |
| Chuỗi thông thường | `"  Mai  "` | `"Mai"` |
| Chuỗi rỗng | `""` | `null` |
| Chuỗi toàn khoảng trắng | `"   "` | `null` |
| String có khoảng trắng bên trong | `" A  B "` | `"A  B"` |
| Chuỗi chữ “null” | `"null"` | `"null"` |
| Input `null` đi qua `setAsText` | `null` | `null` |
| Key bị thiếu trong `MutablePropertyValues` | Không có key | Giữ nguyên giá trị trước đó trên bean |
| Giá trị riêng biệt của field không đăng ký editor | `"   "` | Chuỗi gốc có thể được giữ nguyên |

Cần phân biệt **unit test trực tiếp editor** (kiểm thử `setAsText/getValue`), **unit test binder** (kiểm thử `registerCustomEditor + bind`) và **integration test MVC** (kiểm thử `@InitBinder` có thực sự được gọi và giá trị sau binding/validation). Bất đồng giữa ba lớp test thường giúp tìm ra nguyên nhân chưa đăng ký editor, sai phạm vi hoặc request dùng JSON thay vì form.

## 13. Bài tập tự luyện

Cho class `UpdateContactForm` có ba property String: `displayName`, `bio`, `rawText`. Form gửi:

```text
displayName = "   Linh   "
bio         = "     "
rawText     = "  Keep  these  spaces  "
```

**Yêu cầu:**

1. Dự đoán kết quả nếu đăng ký `new StringTrimmerEditor(true)` cho toàn bộ `String.class`.
2. Dự đoán kết quả nếu dùng `false` thay cho `true`.
3. Đề xuất cách chỉ trim `displayName` và `bio`, nhưng **không thay đổi `rawText`**.
4. Nếu `bio` có `@NotNull`, khác biệt giữa ba cách cấu hình là gì khi `bio` chỉ có khoảng trắng?
5. Vì sao input key `rawText` không xuất hiện trong request thì editor không tự đặt field đó về null?

**Đáp án định hướng:**

- Với editor true cho tất cả String: `displayName="Linh"`, `bio=null`, `rawText="Keep  these  spaces"`; hai đầu bị cắt nhưng hai dấu cách bên trong được giữ.
- Với editor false cho tất cả String: `displayName="Linh"`, `bio=""`, `rawText="Keep  these  spaces"`.
- Để bảo toàn `rawText`, hãy đăng ký editor **theo field**, ví dụ `registerCustomEditor(String.class, "displayName", new StringTrimmerEditor(true))` và thêm một đăng ký tương tự cho `"bio"`.
- `@NotNull` thường coi `bio=null` là không hợp lệ, nhưng coi `bio=""` hoặc `"     "` là không null; muốn cấm chuỗi toàn khoảng trắng bất kể editor thì dùng `@NotBlank`.
- Editor chạy khi field được đưa qua quá trình property binding thích hợp, không tự chuyển đổi những property không có đầu vào.

## 14. Ghi nhớ và tài liệu chính thức

Tóm tắt:

- `StringTrimmerEditor(true)` = **trim** + **đổi kết quả rỗng thành null**.
- `StringTrimmerEditor(false)` = **trim**, nhưng giữ kết quả rỗng dưới dạng `""`.
- `new StringTrimmerEditor(charsToDelete, emptyAsNull)` cho phép xóa những **ký tự tùy chọn ở mọi vị trí** sau trim; sử dụng thận trọng.
- **Phải đăng ký editor** bằng `DataBinder.registerCustomEditor(...)` hoặc cấu hình binder tương ứng; Spring không tự bật trimmer cho mọi `String`.
- `@InitBinder` là chỗ thường dùng trong Spring MVC để đăng ký editor cho model attribute cụ thể.
- Editor không phải validation và không phải sanitizer. Nó làm thay đổi dữ liệu **trước khi các constraint của form thường được đánh giá**.
- Phân biệt **null**, **chuỗi rỗng**, **chuỗi chỉ có khoảng trắng** và **field không được gửi**.

Nguồn tham khảo:

- [Spring Framework — StringTrimmerEditor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/propertyeditors/StringTrimmerEditor.html): constructor, `emptyAsNull`, `setAsText` và `getAsText`.
- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html): các loại `PropertyEditor`, cơ chế binding và việc StringTrimmerEditor không được đăng ký mặc định.
- [Spring Framework — DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/validation/DataBinder.html): `registerCustomEditor`, `bind` và `BindingResult`.
- [Spring Framework — MVC @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html): phạm vi đăng ký converter/formatter/property editor cho request binder.
- [Jakarta Validation — Built-in Constraints](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html): ý nghĩa các constraint như `@NotNull`, `@NotEmpty`, `@NotBlank`, `@Size`.
