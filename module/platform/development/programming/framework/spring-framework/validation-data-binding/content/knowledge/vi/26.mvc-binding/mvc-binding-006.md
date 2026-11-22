# Checkbox, field marker và field default của WebDataBinder trong Spring MVC

## 1. Tại sao checkbox cần xử lý đặc biệt?

Trong HTML, checkbox **được chọn** thường tạo một cặp tham số trong lần gửi form, ví dụ `subscribed=true`. Checkbox **không được chọn** thường **không tạo tham số `subscribed` nào**. Đây là hành vi chuẩn của biểu mẫu HTML, nhưng nó gây một vấn đề khi Spring MVC dùng form để **chỉnh sửa object đã có dữ liệu**.

Giả sử trang “Cài đặt nhận email” hiển thị `subscribed=true`, và người dùng bỏ dấu chọn. Request không có tham số `subscribed`. Nếu binding chỉ cập nhật những thuộc tính có tên trong request, object cũ vẫn có `subscribed=true`: thao tác bỏ chọn đã không được lưu.

**`org.springframework.web.bind.WebDataBinder`** có hai quy ước giải quyết tình huống này:

- **Field marker**: tên tham số bắt đầu bằng dấu gạch dưới, mặc định `_fieldName`. Nó thông báo rằng field có hiện diện trong form dù giá trị thực không được gửi. Nếu thiếu tham số gốc `fieldName`, binder **reset field về giá trị rỗng phù hợp với kiểu dữ liệu**.
- **Field default**: tên tham số bắt đầu bằng dấu chấm than, mặc định `!fieldName`. Nó cung cấp **một giá trị dự phòng xác định** nếu tham số gốc không được gửi; ví dụ `!delivery=NONE`.

Đây là cơ chế của **Spring web data binding** cho form/request parameter, không phải một annotation Bean Validation. Nó thường xuất hiện khi một controller nhận `@ModelAttribute`, dùng `WebDataBinder` để gắn dữ liệu vào bean, rồi có thể gọi validation bằng `@Valid` hoặc `@Validated`.

Bài học sử dụng hành vi của Spring Framework 6.x với Java 17; hai prefix và thứ tự xử lý là cơ chế lâu đời của `WebDataBinder`. Những thiết lập riêng của ứng dụng có thể đổi hoặc tắt prefix.

## 2. Dòng đời dữ liệu: trình duyệt → binder → model

Với checkbox đặt tên `subscribed`:

```html
<form method="post" action="/settings">
    <input type="hidden" name="_subscribed" value="present">
    <label>
        <input type="checkbox" name="subscribed" value="true">
        Nhận thông báo
    </label>
    <button type="submit">Lưu</button>
</form>
```

Giả sử model ban đầu có `subscribed=true`:

| Người dùng gửi form | Các request parameter liên quan | Giá trị sau binding |
| --- | --- | --- |
| Checkbox được chọn | `_subscribed=present`, `subscribed=true` | `true` |
| Checkbox bỏ chọn | Chỉ có `_subscribed=present` | `false` |
| Request không có field và không có marker | Không có tham số liên quan | Giữ giá trị hiện có của object; ở đây vẫn `true` |

Tham số ẩn `_subscribed` **luôn được gửi** khi biểu mẫu có control này. Tham số `subscribed` chỉ được gửi nếu checkbox được chọn. Do đó, marker giúp binder phân biệt **“field đã được hiển thị nhưng rỗng”** với **“field không nằm trong lần cập nhật này”**.

Sơ đồ luồng:

```text
POST /settings
      |
      v
Request parameters
      |
      +-- subscribed=true? ----- yes ---> dùng giá trị thực "true"
      |                              |
      |                              +--> chuyển thành boolean true
      |
      +-- không có subscribed
              |
              +-- có !subscribed? --- yes ---> dùng giá trị mặc định
              |
              +-- không có !subscribed
                      |
                      +-- có _subscribed? -- yes ---> reset về empty value
                      |
                      +-- không có marker ----------> không thay đổi thuộc tính
      |
      v
WebDataBinder + type conversion
      |
      v
Form object nhận giá trị mới
      |
      v
BindingResult / validation (nếu được yêu cầu)
```

**Phân biệt quan trọng**: với một bean mới có primitive `boolean` mặc định là `false`, cả “không gửi gì” và “được reset về `false`” đều có thể tạo kết quả giống nhau. Lỗi chỉ lộ rõ khi **object đã chứa `true`**, hoặc khi kiểu dữ liệu là `Boolean`/collection/string có trạng thái ban đầu khác empty value.

## 3. Field marker: prefix `_` và reset về “rỗng”

### 3.1. Ý nghĩa của `_field`

`WebDataBinder.DEFAULT_FIELD_MARKER_PREFIX` có giá trị mặc định `"_"`. Với field tên `subscribed`, marker là `_subscribed`. Với property path lồng nhau như `preferences.notifications`, marker tương ứng là `_preferences.notifications`.

Một marker **không phải một giá trị của field thật**. Ví dụ:

```text
_subscribed=visible
```

Nó chỉ cho biết field `subscribed` đã có mặt trên form. Giá trị string `"visible"` là tùy ý; binder quan tâm **sự hiện diện** của tham số marker, không quan tâm nội dung của nó.

Cơ chế xử lý ở bước property binding về cơ bản là:

1. Kiểm tra tên tham số có bắt đầu bằng prefix marker hay không.
2. Bỏ prefix để xác định tên field thực.
3. Kiểm tra field được phép gắn dữ liệu và có thuộc tính **writable**.
4. Nếu **chưa có tham số giá trị thực** cho field đó, bổ sung một giá trị rỗng dựa trên kiểu của field.
5. Xóa tham số marker khỏi tập property values trước khi tiếp tục binding thông thường.

Nếu cả `subscribed=true` và `_subscribed=visible` cùng tồn tại, tham số thực `subscribed` **thắng**; marker không thay thế giá trị thật. Nếu không có `subscribed`, marker tạo giá trị rỗng thích hợp.

Marker chỉ xử lý **field được phép bind và có thể ghi**. Nếu field bị loại bởi `setAllowedFields(...)`, hoặc không có property writable tương ứng, marker không buộc binder chỉnh sửa field đó.

### 3.2. “Rỗng” nghĩa là gì?

`WebDataBinder#getEmptyValue(...)` quyết định empty value theo kiểu dữ liệu:

| Kiểu thuộc tính Java | Empty value mặc định khi chỉ gửi marker | Ghi chú |
| --- | --- | --- |
| `boolean` | `false` | Trường hợp checkbox phổ biến |
| `Boolean` | `Boolean.FALSE` | **Không phải `null`** theo mặc định |
| `String` | `null` | Khác với chuỗi rỗng `""` |
| Mảng, ví dụ `String[]` | Mảng độ dài 0 | Có thể reset tập checkbox nhiều lựa chọn |
| `Collection` như `List` hoặc `Set` | Collection rỗng tương thích nếu có thể tạo | Dùng cho nhóm lựa chọn |
| `Map` | Map rỗng tương thích nếu có thể tạo | Áp dụng khi field hỗ trợ binding |
| Kiểu khác (ví dụ `Integer`) | Thường là `null` | Trừ khi ứng dụng/provider tùy biến cơ chế tạo empty value |

Spring cung cấp cả `getEmptyValue(Class<?>)` và biến thể protected `getEmptyValue(String, Class<?>)`. Ứng dụng rất đặc thù có thể subclass binder và đổi cách chọn empty value, nhưng code thông thường nên dựa vào bảng mặc định và viết test biên cho kiểu dữ liệu đang dùng.

**Không hiểu nhầm:** marker `_subscribed` không biến thành một trường tên `_subscribed` trên bean. Spring xử lý prefix, sau đó bind vào `subscribed`. Nếu bạn đặt tên field thực bắt đầu bằng các prefix đặc biệt, hãy cân nhắc đổi cấu hình prefix để tránh xung đột.

### 3.3. Mảng hoặc nhiều checkbox cùng tên

Với các checkbox cùng tên `interests`, mỗi checkbox được chọn có thể gửi một giá trị:

```html
<input type="hidden" name="_interests" value="present">
<label><input type="checkbox" name="interests" value="JAVA"> Java</label>
<label><input type="checkbox" name="interests" value="SPRING"> Spring</label>
```

Nếu cả hai đều không được chọn, request chỉ có `_interests`, vì vậy field mảng `String[] interests` có thể được reset thành **mảng rỗng**. Nếu `interests` là `List<String>`, Spring có thể gán collection rỗng.

Chỉ cần **một marker logic** cho cùng field. Các template tag có thể sinh marker ẩn cạnh từng checkbox; quan trọng là binder nhận biết sự tồn tại của marker. Nếu request có nhiều lần lặp cùng key marker, nên giữ cú pháp form đơn giản và dùng test thực tế với template engine đang triển khai.

## 4. Field default: prefix `!` và giá trị thay thế

`WebDataBinder.DEFAULT_FIELD_DEFAULT_PREFIX` có giá trị mặc định `"!"`. Ví dụ:

```html
<input type="hidden" name="!delivery" value="NONE">
<label><input type="radio" name="delivery" value="EMAIL"> Email</label>
<label><input type="radio" name="delivery" value="SMS"> SMS</label>
```

Nếu user không chọn radio và không có tham số `delivery`, binder có thể dùng `NONE` từ `!delivery`. Khi user chọn `SMS`, tham số `delivery=SMS` chiếm ưu tiên, nên giá trị hidden default bị bỏ qua.

**Khác biệt:** field marker chỉ báo “đã có control nhưng không gửi giá trị, hãy reset rỗng”; field default mang **giá trị cụ thể** (ví dụ `"NONE"`, `"false"`, `"0"`), và giá trị đó được chuyển đổi sang kiểu property khi binding.

Một field có thể có cả marker và default:

```text
_subscribed=visible
!subscribed=true
```

Nếu thiếu tham số `subscribed`, binder dùng `"true"` của field default. Nó **không** reset `false` từ marker. Tại bước xử lý property values, Spring chạy **`checkFieldDefaults(...)` trước `checkFieldMarkers(...)`**, nên mặc định ưu tiên hơn marker.

### 4.1. Thứ tự ưu tiên đầy đủ

Với field boolean `subscribed` mà object hiện có `true`:

| Request parameters | Nguồn được chọn | Kết quả |
| --- | --- | --- |
| `subscribed=false`, `!subscribed=true`, `_subscribed=x` | Giá trị thực `subscribed` | `false` |
| `subscribed=true`, `_subscribed=x` | Giá trị thực `subscribed` | `true` |
| `!subscribed=true`, `_subscribed=x` | Default `!subscribed` | `true` |
| `_subscribed=x` | Marker yêu cầu empty value | `false` |
| `!subscribed=false` | Default `!subscribed` | `false` |
| Không có ba tham số | Không có update cho property | Giữ `true` |

Có thể ghi nhớ thứ tự:

**Giá trị thực `field` → giá trị mặc định `!field` → reset do marker `_field` → giữ trạng thái nếu hoàn toàn vắng mặt.**

Quy tắc trên chỉ nói về cơ chế binding; nếu property không được phép bind, không writable hoặc có lỗi chuyển kiểu, kết quả cần xử lý thông qua cấu hình binding và `BindingResult`.

### 4.2. Field default khác default của Java/DTO

Một field khởi tạo sẵn:

```java
private boolean subscribed = true;
```

là **giá trị mặc định của object** khi tạo instance. Còn `!subscribed=false` là **request parameter do client gửi**. Hai cơ chế độc lập:

- Field **không được submit**: nếu binding trên object sẵn có, giá trị có thể giữ nguyên.
- Có marker nhưng không có field thật/default: binder reset theo type.
- Có field default: binder có thể ghi đè trạng thái khởi tạo bằng giá trị từ request.
- Có field thật: field thật được dùng.

Không dùng `!role=ADMIN`, `!isAdmin=true` hay default do client điều khiển để cấp quyền. Quyền và invariant phải được xác định ở server, không dựa vào tham số hidden.

## 5. Ví dụ Java 17 chạy được: kiểm tra hành vi của WebDataBinder

Ví dụ này gọi `WebDataBinder` trực tiếp, **không cần khởi động web server**. Nó mô phỏng dữ liệu request bằng `MutablePropertyValues` và in ra kết quả sau mỗi lần bind để thấy rõ precedence của `field`, `!field` và `_field`. Vì mỗi scenario tạo form mới, các kết quả độc lập và dễ kiểm chứng.

### 5.1. Cấu trúc dự án

```text
webdatabinder-checkbox-demo/
├── pom.xml
└── src/main/java/demo/BinderDemo.java
```

### 5.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>webdatabinder-checkbox-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-web</artifactId>
            <version>6.2.12</version>
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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.BinderDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Dependency `spring-web` chứa `WebDataBinder`, còn các lớp `MutablePropertyValues` và binding cần thiết được Spring đưa vào qua dependency bắc cầu. Ví dụ chọn cùng một phiên bản Spring 6.2.x và JDK 17; không cần `spring-boot-starter-web` nếu chỉ chạy thử API binder.

### 5.3. `src/main/java/demo/BinderDemo.java`

```java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.web.bind.WebDataBinder;

public final class BinderDemo {

    // JavaBean với setter public để WebDataBinder property binding.
    public static final class SettingsForm {
        private boolean subscribed = true;
        private String delivery = "EMAIL";
        private String[] interests = {"JAVA", "SPRING"};
        private List<String> roles = new ArrayList<>(List.of("USER"));

        public boolean isSubscribed() {
            return subscribed;
        }
        public void setSubscribed(boolean subscribed) {
            this.subscribed = subscribed;
        }

        public String getDelivery() {
            return delivery;
        }
        public void setDelivery(String delivery) {
            this.delivery = delivery;
        }

        public String[] getInterests() {
            return interests;
        }
        public void setInterests(String[] interests) {
            this.interests = interests;
        }

        public List<String> getRoles() {
            return roles;
        }
        public void setRoles(List<String> roles) {
            this.roles = roles;
        }
    }

    private static void scenario(
            String name, Consumer<MutablePropertyValues> input) {
        SettingsForm form = new SettingsForm();
        WebDataBinder binder = new WebDataBinder(form, "settings");

        // Chỉ cho phép các property của biểu mẫu demo.
        binder.setAllowedFields(
                "subscribed", "delivery", "interests", "roles");

        MutablePropertyValues values = new MutablePropertyValues();
        input.accept(values);
        binder.bind(values);

        if (binder.getBindingResult().hasErrors()) {
            throw new IllegalStateException(
                    binder.getBindingResult().toString());
        }

        System.out.printf(
                "%s: subscribed=%s, delivery=%s, interests=%d, roles=%d%n",
                name,
                form.isSubscribed(),
                form.getDelivery(),
                form.getInterests().length,
                form.getRoles().size());
    }

    public static void main(String[] args) {
        scenario("No fields", p -> {});

        scenario("Unchecked", p ->
                p.add("_subscribed", "visible"));

        scenario("Checked", p -> {
            p.add("_subscribed", "visible");
            p.add("subscribed", "true");
        });

        scenario("Default delivery", p ->
                p.add("!delivery", "NONE"));

        scenario("Explicit beats default", p -> {
            p.add("!delivery", "NONE");
            p.add("delivery", "SMS");
        });

        scenario("Default beats marker", p -> {
            p.add("_subscribed", "visible");
            p.add("!subscribed", "true");
        });

        scenario("Reset interests", p ->
                p.add("_interests", "visible"));

        scenario("Reset roles", p ->
                p.add("_roles", "visible"));

        scenario("Reset delivery", p ->
                p.add("_delivery", "visible"));
    }
}
```

Đây là một chương trình **hoàn chỉnh**. Các field có getter và setter public; binder sử dụng JavaBean property binding, không cần truy cập trực tiếp vào field private. `setAllowedFields(...)` làm rõ phạm vi đầu vào được phép, nhưng ví dụ không kiểm thử một endpoint HTTP thật.

Chạy bằng JDK 17+ và Maven trong thư mục dự án:

```bash
mvn -q clean compile exec:java
```

**stdout của chương trình** (không tính log Maven nếu có):

```text
No fields: subscribed=true, delivery=EMAIL, interests=2, roles=1
Unchecked: subscribed=false, delivery=EMAIL, interests=2, roles=1
Checked: subscribed=true, delivery=EMAIL, interests=2, roles=1
Default delivery: subscribed=true, delivery=NONE, interests=2, roles=1
Explicit beats default: subscribed=true, delivery=SMS, interests=2, roles=1
Default beats marker: subscribed=true, delivery=EMAIL, interests=2, roles=1
Reset interests: subscribed=true, delivery=EMAIL, interests=0, roles=1
Reset roles: subscribed=true, delivery=EMAIL, interests=2, roles=0
Reset delivery: subscribed=true, delivery=null, interests=2, roles=1
```

### 5.4. Phân tích từng tình huống

- **No fields:** request không có tên field thật, marker hay default; binder không có lý do ghi đè state ban đầu.
- **Unchecked:** có `_subscribed` nhưng thiếu `subscribed`; `getEmptyValue(boolean.class)` chọn `false`.
- **Checked:** có cả field thật và marker; `subscribed=true` được chuyển kiểu và có ưu tiên.
- **Default delivery:** `!delivery=NONE` được dùng vì không có tham số `delivery`.
- **Explicit beats default:** `delivery=SMS` có ưu tiên hơn `!delivery=NONE`.
- **Default beats marker:** `!subscribed=true` được áp dụng trước marker; giá trị true giữ lại thay vì reset false.
- **Reset interests:** `_interests` thay mảng hai phần tử bằng mảng độ dài 0.
- **Reset roles:** `_roles` thay collection có một giá trị bằng collection rỗng.
- **Reset delivery:** `_delivery` đưa `String` về `null`, không tự tạo `""`.

Code in ra **độ dài mảng và collection** thay vì implementation type của collection để stdout ổn định và tập trung vào semantics. Với request production, nếu một tham số có nhiều giá trị (nhiều checkbox được chọn), Spring còn phải chuyển chuỗi/mảng request sang kiểu property phù hợp; ví dụ tránh sự không chắc chắn đó bằng cách chỉ mô phỏng các tình huống biên.

## 6. Dùng trong controller Spring MVC với `@ModelAttribute`

Trong Spring Web MVC, `WebDataBinder` thường được tạo riêng cho một lần gắn tham số vào command object. Bạn có thể cấu hình binder qua `@InitBinder`.

Ví dụ dưới đây là **fragment tích hợp trong ứng dụng Spring Boot 3 có Spring Web**, không phải class Java độc lập để chạy chỉ với `pom.xml` của demo trước:

```java
import org.springframework.stereotype.Controller;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;

@Controller
public class SettingsController {
    @InitBinder("settings")
    void initSettingsBinder(WebDataBinder binder) {
        binder.setAllowedFields(
                "subscribed", "delivery", "interests");
        // Prefix mặc định "_" và "!" đã đủ cho form HTML.
    }

    @PostMapping("/settings")
    String update(
            @ModelAttribute("settings") SettingsForm form,
            BindingResult bindingResult) {

        if (bindingResult.hasErrors()) {
            return "settings-form";
        }

        // Lưu các field được phép của form vào domain model.
        return "redirect:/settings";
    }
}
```

`SettingsForm` là model/form class cần định nghĩa trong dự án web; có thể dựa trên JavaBean trong demo nhưng nên chọn thuộc tính đúng mục đích endpoint. `BindingResult` phải nằm ngay sau đối số model mà nó mô tả để Spring ghép lỗi chính xác.

Nếu muốn chạy Jakarta Bean Validation sau binding, đặt `@Valid`/`@Validated` trên model parameter và có provider Jakarta Validation phù hợp. Checkbox marker vẫn được xử lý trong giai đoạn **binding**; Bean Validation là giai đoạn kiểm tra giá trị **sau khi đã gắn dữ liệu**.

### 6.1. HTML thủ công và Spring form tags

Nếu tạo form HTML trực tiếp, hãy tự thêm hidden marker:

```html
<input type="hidden" name="_subscribed" value="1">
<input type="checkbox" name="subscribed" value="true">
```

Khi render bằng **JSP Spring Form Tag Library**, thẻ `<form:checkbox path="subscribed"/>` thường sinh thêm hidden marker theo convention `_subscribed`. Hãy kiểm tra HTML sau render vì template engine khác, JavaScript custom controls và UI frameworks có thể xử lý checkbox theo cách riêng.

Ví dụ fragment JSP trong form đã gắn modelAttribute:

```jsp
<form:form modelAttribute="settings" method="post">
    <form:checkbox path="subscribed" label="Nhận thông báo"/>
    <button type="submit">Lưu</button>
</form:form>
```

Đây là fragment JSP yêu cầu Spring form taglib được khai báo trong file JSP và controller chuẩn bị modelAttribute tương ứng. Khi xem HTML thực tế, cần xác nhận hidden marker được submit cùng form dù checkbox đang bỏ chọn.

### 6.2. Cấu hình prefix khi form đặc biệt

`WebDataBinder` cung cấp:

```java
@InitBinder("settings")
void configure(WebDataBinder binder) {
    binder.setFieldMarkerPrefix("_");
    binder.setFieldDefaultPrefix("!");
    binder.setAllowedFields("subscribed", "delivery", "interests");
}
```

Đây là fragment trong controller. Hai lời gọi set prefix chỉ viết rõ **giá trị mặc định**, thông thường không cần. Nếu framework frontend đã dùng những tên khác, có thể đổi:

```java
binder.setFieldMarkerPrefix("~");
binder.setFieldDefaultPrefix("$");
```

Khi đó marker phải tên `~subscribed` và default phải tên `$subscribed`. Cả phần render form lẫn phần bind phải dùng **cùng quy ước**; đổi một phía sẽ khiến reset/default không hoạt động.

- `setFieldMarkerPrefix(null)`: tắt hoàn toàn xử lý field marker.
- `setFieldDefaultPrefix(null)`: tắt xử lý field default.

Việc tắt prefix có thể phù hợp một giao thức client đã được thiết kế khác, nhưng phải có test chứng minh trạng thái **bỏ chọn/không chọn** được cập nhật đúng.

## 7. Field marker khác gì các cơ chế khác của Spring?

| Cơ chế | Giai đoạn | Dùng để giải quyết |
| --- | --- | --- |
| `WebDataBinder` field marker `_field` | HTTP form/request parameter → object property | Phân biệt field có mặt nhưng không gửi giá trị |
| `WebDataBinder` field default `!field` | HTTP form/request parameter → object property | Cấp giá trị fallback khi field thật vắng mặt |
| `@ModelAttribute` | Spring MVC argument resolution | Tạo/tìm model và bind request vào thuộc tính |
| `ConversionService` / property editor | Type conversion | Chuyển `"true"`, `"3"`, date string thành kiểu Java |
| `@Valid` / `@Validated` | Validation | Kiểm tra các constraint sau binding |
| `BindingResult` | Báo lỗi binding/validation | Ghi nhận lỗi chuyển kiểu, lỗi constraint |
| `@RequestBody` với JSON/Jackson | HTTP message conversion | Parse JSON thành object; **không dựa vào marker `_field` của form binding** |
| `@RequestParam` đơn lẻ | Lấy request parameter | Đọc tham số riêng lẻ, không tương đương gắn nhiều property của `@ModelAttribute` |

Ví dụ, JSON:

```json
{"subscribed": false}
```

là một giá trị boolean **tường minh**. Nếu client gửi JSON `{}`, field không có mặt; semantics của trường thiếu phụ thuộc Jackson, constructor, mặc định của object và logic update. Gửi key JSON `"_subscribed"` không tự kích hoạt convention của `WebDataBinder` trong quá trình JSON message conversion.

Với API REST có semantics PATCH hoặc partial update, **không tự động đồng nhất “vắng mặt” với “false”**. Một PATCH có thể yêu cầu giữ nguyên giá trị khi trường không có trong payload; một POST form chỉnh sửa toàn bộ có thể cần reset checkbox không được chọn. Chọn ngữ nghĩa theo API contract.

## 8. Bảo mật và tính toàn vẹn dữ liệu

Marker và default do **client gửi**, kể cả chúng nằm trong hidden input. Bất cứ client nào cũng có thể sửa `_field`, `!field` hoặc gửi thêm field thật thủ công. Vì thế:

1. **Chỉ bind những field endpoint cho phép**. Dùng form/DTO chuyên dụng và `binder.setAllowedFields(...)`, chẳng hạn `"subscribed"`, `"delivery"`, `"interests"`. Đây là allowlist, không phải danh sách gợi ý.
2. **Không bind trực tiếp toàn bộ entity/domain object** chứa role, account id, status, price, quyền admin hoặc field nội bộ mà không giới hạn writable properties.
3. **Không dùng `!isAdmin=true` làm mặc định bảo mật.** Giá trị hidden cũng không đáng tin hơn các trường khác.
4. **Validate dữ liệu sau binding**, ví dụ giới hạn số lựa chọn, giá trị enum hợp lệ, điều kiện phụ thuộc nhiều thuộc tính; validation không thay thế kiểm tra authorization.
5. **Bảo vệ CSRF cho HTML form thay đổi trạng thái** theo cấu hình Spring Security, độc lập với marker. Một field hidden marker không phải CSRF token.
6. **Kiểm tra allowed fields trước khi reset**: Spring xử lý marker/default cho các property được phép và writable. Việc không allowlist khiến attacker có thể nhắm vào các thuộc tính mà form UI không dự định thay đổi.
7. **Không bỏ qua binding errors.** Nếu `!delivery` chứa giá trị không chuyển thành kiểu property được, lỗi cần được nhận qua `BindingResult` hoặc cơ chế xử lý phù hợp.

Đối với application nhiều field phức tạp, nên tách các form object cho từng use case thay vì dùng một model khổng lồ chứa mọi thuộc tính của entity. Điều đó giúp marker của form này không vô tình reset dữ liệu thuộc form khác.

## 9. Các trường hợp biên và lỗi thường gặp

### 9.1. Checkbox bỏ chọn nhưng object vẫn `true`

**Triệu chứng:** edit form hiển thị checkbox được chọn, người dùng bỏ chọn rồi lưu, refresh vẫn hiển thị được chọn.

**Nguyên nhân phổ biến:** request không có `subscribed`, không có `_subscribed`; binder không phân biệt “bỏ chọn” với “không gửi field”.

**Sửa:** đặt hidden marker nằm bên trong form và cùng base name:

```html
<input type="hidden" name="_subscribed" value="present">
<input type="checkbox" name="subscribed" value="true">
```

Kiểm tra Network → Form Data của trình duyệt. Khi bỏ chọn, request vẫn phải có `_subscribed`.

### 9.2. Gửi `_field=false` nhưng field không thay đổi như mong muốn

`_field` **không chứa giá trị reset**. Binder chỉ kiểm tra sự hiện diện. Với String, empty value là `null`; với array là mảng rỗng; với Boolean là `false`. Nếu muốn một giá trị chính xác khác “rỗng”, dùng `!field=desiredValue`.

### 9.3. Đã có cả marker và default nhưng mong marker thắng

Theo thứ tự `checkFieldDefaults` → `checkFieldMarkers`, default được áp dụng trước khi marker xử lý. Khi default tạo field thật, marker thấy field đã có và không reset. Nếu muốn reset theo marker, **không** gửi đồng thời một default làm thay đổi kết quả.

### 9.4. Dùng `_field` cho field thực sự không tồn tại

Nếu property không writable hoặc không nằm trong allowlist, marker không tạo ra một property hợp lệ. Đừng mong có `_permissions` là binder sẽ tự sinh thêm một property `permissions` trên DTO.

### 9.5. `Boolean` có ba trạng thái nhưng marker xóa mất `null`

Khi field là `Boolean`, marker mặc định reset thành `Boolean.FALSE`, **không phải `null`**. Nếu nghiệp vụ cần phân biệt “không trả lời” (null) và “trả lời không” (false), cần mô hình input phù hợp, ví dụ radio với các lựa chọn tường minh hoặc một DTO state riêng, thay vì xem checkbox boolean tự giữ được ba trạng thái.

### 9.6. Có nhiều checkbox mà giá trị cũ không được xóa

Nếu một group gửi các value khi được chọn nhưng **không gửi marker khi không lựa chọn nào được chọn**, tập lựa chọn cũ có thể còn nguyên. Thêm `_interests`/`_roles` vào form và test tình huống chọn tất cả → bỏ chọn tất cả. Đảm bảo thuộc tính đích là array/Collection phù hợp và có thể bind.

### 9.7. Checkbox của thư viện frontend không dùng native HTML submit

Nhiều UI component render một nút hoặc div thay vì `<input type="checkbox">`, và tự serialize dữ liệu. Khi đó hãy kiểm tra payload thực tế. Nếu client chủ động gửi `subscribed=false`, không cần marker để bù cho tham số bị thiếu. Nếu client bỏ hẳn field khi false, cần quy ước tương ứng.

### 9.8. Marker trong form nhưng không được gửi

Hidden input có thể nằm ngoài thẻ `<form>`, bị `disabled`, bị JavaScript bỏ khỏi payload, hoặc khác tên property. Bản thân attribute `hidden` của HTML không tạo yêu cầu gì cho server; chỉ request parameter thực tế mới quan trọng.

### 9.9. Gửi request JSON rồi mong `_field` tác động

Khi endpoint dùng `@RequestBody` và Jackson, payload được giải mã thành object bởi HTTP message converter. Quy ước `_field`, `!field` trong `WebDataBinder` không tự thực thi trong quá trình deserialization. Với JSON, nên định nghĩa ngữ nghĩa giá trị false, null và missing rõ ràng trong schema/contract của API.

### 9.10. Biến mất error của form sau khi bind

Field marker xử lý giá trị, không xóa quy tắc validation. Khi một field bị reset về `null` hoặc empty collection, có thể xuất hiện lỗi `@NotNull`, `@NotEmpty` hoặc constraint khác. Controller phải đọc `BindingResult` và hiển thị lỗi phù hợp; không tự xem “unchecked” là luôn hợp lệ.

## 10. Kiểm thử có hệ thống

Các test tích hợp bằng Spring MVC có thể dùng `MockMvc` và kiểm tra cả form data thực tế. Danh sách tình huống nên bao phủ:

| Input / trạng thái ban đầu | Kết quả mong đợi |
| --- | --- |
| `subscribed=true` ban đầu, chỉ `_subscribed` | `subscribed=false` |
| `subscribed=true` ban đầu, không có bất kỳ field liên quan | `subscribed=true` (nếu bind trên object hiện có) |
| `subscribed=false` ban đầu, `subscribed=true` và marker | `subscribed=true` |
| `delivery=EMAIL` ban đầu, chỉ `!delivery=NONE` | `delivery=NONE` |
| Cả `delivery=SMS` và `!delivery=NONE` | `delivery=SMS` |
| Cả `!subscribed=true` và `_subscribed` | Default `true` thắng marker |
| `String[] interests` có dữ liệu, chỉ `_interests` | Mảng độ dài 0 |
| `List<String> roles` có dữ liệu, chỉ `_roles` | Collection rỗng |
| `String delivery` có dữ liệu, chỉ `_delivery` | `null` |
| Marker/default cho field ngoài allowlist | Không cập nhật field bị cấm |
| Giá trị thực không chuyển kiểu được | Binding error được báo đúng |
| Dùng `setFieldMarkerPrefix(null)` | Marker không tự reset |

Một số test cần phân biệt rõ **model đã có dữ liệu** với **model mới tạo**. Nếu chỉ test boolean primitive mới mặc định false, test có thể “pass” mà không chứng minh marker hoạt động. Để phát hiện đúng bug, khởi tạo giá trị đầu là `true`, sau đó thử form unchecked.

Đối với controller, kiểm tra response và giá trị mà application thực sự lưu, không chỉ nội dung HTML trả về. Dùng tên field chính xác trong `MockMvc.param(...)`, chẳng hạn `.param("_subscribed", "present")`. Nếu endpoint lưu trữ domain entity, hãy đảm bảo quá trình map từ form DTO sang entity thực sự áp giá trị false mới.

## 11. Checklist triển khai form checkbox đáng tin cậy

- [ ] Xác định rõ property name, kiểu dữ liệu và trạng thái trước/sau thao tác.
- [ ] Nếu unchecked không gửi giá trị thật, thêm hidden marker có tên `_field`.
- [ ] Nếu cần giá trị fallback không rỗng, thêm `!field=value`.
- [ ] Không gửi default khi thực sự muốn hành vi reset của marker.
- [ ] Giữ thống nhất tên field thật, marker/default và tên property JavaBean.
- [ ] Với group checkbox, kiểm tra tình huống **tất cả không được chọn**.
- [ ] Dùng form DTO chuyên dụng và allowlist field có thể bind.
- [ ] Xác nhận template engine tạo/không tạo marker bằng cách xem HTML và HTTP request.
- [ ] Xử lý `BindingResult` và validation sau binding khi cần.
- [ ] Viết test trên object đã có giá trị ban đầu khác rỗng.
- [ ] Không áp dụng ngầm quy ước form marker sang JSON/PATCH API.
- [ ] Khi đổi prefix hoặc tắt prefix, cập nhật cả phía tạo request và test.

**Nguyên tắc thực hành:** trong form HTML, sự **vắng mặt của tham số** không đồng nghĩa với giá trị `false`. `_field` nói rằng field có mặt trên form nên cần reset nếu không có value; `!field` cung cấp fallback cụ thể; tham số thật `field` có ưu tiên cao nhất. Nắm thứ tự đó và kiểm tra payload thực tế sẽ giúp cập nhật checkbox, radio, danh sách lựa chọn và các trường có thể rỗng một cách dự đoán được.

## Tài liệu tham khảo

- [Spring Framework 6.2 WebDataBinder Javadoc — marker, default, empty value](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/bind/WebDataBinder.html)
- [Spring Framework 6.2 reference — `@InitBinder` và allowed fields](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework 6.2 reference — JSP Spring Form Tag checkbox](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc-view/mvc-jsp.html)
- [Spring Framework source — `WebDataBinder.java`](https://github.com/spring-projects/spring-framework/blob/6.2.x/spring-web/src/main/java/org/springframework/web/bind/WebDataBinder.java)
