# `setAsText`, `getAsText` và trạng thái giá trị bên trong `PropertyEditor`

## 1. `PropertyEditor` dùng để làm gì?

`java.beans.PropertyEditor` là giao diện trong JavaBeans API cho phép chuyển đổi và chỉnh sửa giá trị của một property. Trong Spring Framework, các `PropertyEditor` thường được sử dụng tại hạ tầng property access và data binding để chuyển đổi dữ liệu dạng chuỗi (ví dụ request parameter) thành giá trị Java như `Date`, enum hoặc value object tùy biến.

Điểm rất quan trọng: `PropertyEditor` **có trạng thái**. Thay vì thiết kế như một hàm thuần `String -> T`, editor giữ **giá trị hiện tại** bên trong. Phương thức `setAsText(String)` nhận chuỗi, parse rồi thường gọi `setValue(Object)` để lưu giá trị; `getAsText()` đọc giá trị hiện tại qua `getValue()` và xuất ra chuỗi.

```text
Input text "42"
       |
       v
editor.setAsText("42")
       |
       v
parse String -> Integer(42)
       |
       v
editor.setValue(42)            <-- trạng thái bên trong editor
       |
       +--> editor.getValue()  -> Integer(42)
       |
       +--> editor.getAsText() -> "42"
```

Trong bài này cần phân biệt **text representation**, **value được lưu trong editor**, và **giá trị cuối cùng được binder gán vào property**. Chúng liên quan nhau nhưng không phải ba đối tượng đồng nhất.

## 2. Bốn phương thức quan trọng

| API | Vai trò | Điểm cần nhớ |
| --- | --- | --- |
| `setAsText(String text)` | Nhận chuỗi và yêu cầu editor chuyển sang value | Có thể ném `IllegalArgumentException` khi parse không thành công |
| `getAsText()` | Trả representation dạng chuỗi của value hiện tại | Có thể là chuỗi chuẩn hóa, không nhất thiết giống input ban đầu |
| `setValue(Object value)` | Đặt value đang được editor giữ | Được định nghĩa bởi `PropertyEditor`, có thể được hỗ trợ thông qua `PropertyEditorSupport` |
| `getValue()` | Lấy value hiện tại | Có thể trả `null` nếu chưa có value hoặc đã được đặt thành `null` |

`PropertyEditor` còn khai báo những API phục vụ JavaBeans design-time như tags/custom editor và property change listeners. Trong Spring data binding, bốn phương thức trên thường là trọng tâm. Khi tự viết editor, đa số ứng dụng kế thừa `java.beans.PropertyEditorSupport` thay vì tự triển khai mọi phương thức của `PropertyEditor`.

### `setAsText` không trả giá trị

Chữ ký của API là `void setAsText(String text)`, **không** phải `T convert(String text)`. Cách đúng là:

```java
editor.setAsText("42");
Object result = editor.getValue();
```

Giá trị được editor giữ bằng state sau khi parsing. Nếu text không hợp lệ, implementation nên báo lỗi rõ ràng; không nên âm thầm giữ value cũ rồi khiến caller hiểu nhầm lần parse đã thành công.

### `getAsText` không phải luôn là phép nghịch đảo tuyệt đối

Ví dụ input `"00042"` có thể được parse thành số nguyên `42`, rồi trả `"42"` từ `getAsText()`. Đây là **chuẩn hóa representation**. Không có bảo đảm rằng `getAsText()` phải giữ nguyên whitespace, leading zeros hoặc mọi chi tiết chuỗi ban đầu.

## 3. Ví dụ Java 17+ chạy được: editor cho mã sản phẩm

Ví dụ dưới chỉ dùng JavaBeans API của JDK, **không cần Spring dependency**. Tạo file `PropertyEditorStateDemo.java`:

```java
import java.beans.PropertyEditorSupport;

public class PropertyEditorStateDemo {
    public record ProductCode(String value) {}

    public static class ProductCodeEditor extends PropertyEditorSupport {
        @Override
        public void setAsText(String text) {
            if (text == null) {
                setValue(null);
                return;
            }
            String normalized = text.trim().toUpperCase();
            if (!normalized.matches("P-[0-9]{4}")) {
                throw new IllegalArgumentException("Invalid product code");
            }
            setValue(new ProductCode(normalized));
        }

        @Override
        public String getAsText() {
            ProductCode code = (ProductCode) getValue();
            return code == null ? "" : code.value();
        }
    }

    public static void main(String[] args) {
        ProductCodeEditor editor = new ProductCodeEditor();
        editor.setAsText(" p-0042 ");

        System.out.println(editor.getValue());
        System.out.println(editor.getAsText());

        editor.setValue(new ProductCode("P-0007"));
        System.out.println(editor.getAsText());

        editor.setAsText(null);
        System.out.println(editor.getValue() == null);
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac PropertyEditorStateDemo.java
java PropertyEditorStateDemo
```

Stdout chính xác:

```text
ProductCode[value=P-0042]
P-0042
P-0007
true
```

Giải thích trạng thái theo thời gian:

1. Lúc mới tạo, editor chưa có value; `PropertyEditorSupport` có giá trị ban đầu `null`.
2. `setAsText(" p-0042 ")` cắt khoảng trắng, chuyển uppercase, validate pattern, đặt value là `ProductCode("P-0042")`.
3. `getValue()` trả record đó, còn `getAsText()` trả `"P-0042"`.
4. `setValue(new ProductCode("P-0007"))` **thay thế trực tiếp** state; `getAsText()` ngay sau đó xuất `"P-0007"` mà không chạy lại `setAsText`.
5. `setAsText(null)` được implementation này quy ước xóa state; mỗi custom editor có thể chọn quy tắc khác nhưng cần nhất quán và được tài liệu hóa.

Không coi editor là hàm chuyển đổi bất biến. Trạng thái có thể thay đổi qua cả `setAsText` và `setValue`.

## 4. Trạng thái editor ảnh hưởng việc dùng lại như thế nào?

`PropertyEditorSupport` chứa value mutable; một editor có thể đang giữ kết quả parse của lần gọi trước. Ví dụ:

```java
var editor = new PropertyEditorStateDemo.ProductCodeEditor();
editor.setAsText("P-0001");
System.out.println(editor.getAsText());  // P-0001
editor.setAsText("P-0002");
System.out.println(editor.getAsText());  // P-0002
```

Đoạn này minh họa state và giả định class ví dụ ở mục 3 đã được biên dịch. `getAsText()` luôn mô tả **giá trị hiện tại**, không phải lịch sử input. Việc dùng lại editor theo thứ tự là có thể trong một luồng kiểm soát được, nhưng không nên dùng cùng một instance editor mutable như singleton chia sẻ giữa nhiều request hoặc threads.

### Thread-safety và vòng đời

- Không giả định `PropertyEditorSupport` thread-safe. Nhiều editor có value nội bộ và không có cơ chế đồng bộ hóa phù hợp cho request độc lập.
- Một bean editor singleton có thể tạo race condition: request A gọi `setAsText`, request B thay đổi value, request A đọc `getValue()` sai dữ liệu.
- Với Spring, nên để binder/property access dùng editor instance theo vòng đời thích hợp hoặc dùng cơ chế đăng ký editor factory/registrar phù hợp; không chia sẻ bừa một editor đang giữ state.
- Nếu chỉ cần logic chuyển đổi không có state, Spring `Converter<S,T>` hoặc `Formatter<T>` thường là abstraction dễ tái sử dụng hơn.

## 5. Tích hợp với Spring `DataBinder`

`DataBinder` có thể đăng ký editor cho một kiểu và dùng editor trong quá trình property binding. Giả sử một form chứa thuộc tính `ProductCode`:

```java
public class ProductForm {
    private PropertyEditorStateDemo.ProductCode code;

    public PropertyEditorStateDemo.ProductCode getCode() { return code; }
    public void setCode(PropertyEditorStateDemo.ProductCode code) {
        this.code = code;
    }
}
```

Đây là một class mẫu dùng cùng `ProductCode` đã khai báo ở ví dụ chính. Đoạn đăng ký trong method Java có biến `form`:

```java
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.DataBinder;

DataBinder binder = new DataBinder(form, "productForm");
binder.registerCustomEditor(
        PropertyEditorStateDemo.ProductCode.class,
        new PropertyEditorStateDemo.ProductCodeEditor());

MutablePropertyValues values = new MutablePropertyValues();
values.add("code", " p-0042 ");
binder.bind(values);

System.out.println(form.getCode());
System.out.println(binder.getBindingResult().hasErrors());
```

Output mong đợi khi class, dependencies và binder được cấu hình đúng:

```text
ProductCode[value=P-0042]
false
```

Luồng xử lý: `DataBinder` tìm property `code` kiểu `ProductCode`, dùng `ProductCodeEditor` để chuyển String sang value rồi gán value vào setter. Mọi lỗi chuyển đổi được báo qua binding error nếu phù hợp với cơ chế binder. Việc đăng ký custom editor không tự động chạy validation nghiệp vụ.

Đây là **snippet tích hợp**, không phải chương trình độc lập: cần class `ProductForm`, class ví dụ chính và Spring modules tương thích trên classpath. Với những kiểu chuẩn, Spring đã có conversion/editor mặc định; không cần viết editor riêng cho mọi property.

## 6. Đăng ký theo kiểu hoặc theo property path

Spring cho phép đăng ký editor theo kiểu đích và, trong các API hỗ trợ, theo một đường dẫn property cụ thể:

```java
binder.registerCustomEditor(ProductCode.class, new ProductCodeEditor());
binder.registerCustomEditor(ProductCode.class, "primaryCode",
        new ProductCodeEditor());
```

Đây là snippet giả định các class `ProductCode` và `ProductCodeEditor` đã được import từ ví dụ chính và object target có property `primaryCode` phù hợp. Lệnh đầu áp dụng cho những property có kiểu `ProductCode` theo phạm vi của binder; lệnh sau ràng buộc editor vào property path `primaryCode`.

Phạm vi theo path có ích nếu cùng kiểu Java nhưng cách nhập/hiển thị khác nhau giữa các trường. Tuy nhiên không lạm dụng editor theo path đến mức conversion phụ thuộc ngẫu nhiên vào tên trường khó bảo trì.

## 7. Phân biệt parse, print và validation

| Thao tác | Điểm vào | Đầu ra |
| --- | --- | --- |
| Parse text thành value | `setAsText(text)` | Side effect lên `getValue()` hoặc exception |
| Xuất value hiện tại ra text | `getAsText()` | `String` |
| Đặt value trực tiếp | `setValue(value)` | Cập nhật state của editor |
| Data binding | `DataBinder.bind(PropertyValues)` | Target được gán và `BindingResult` ghi lỗi |
| Validation | `Validator.validate(...)` | Lỗi nghiệp vụ trong `Errors` |

Một mã sản phẩm có thể đúng cú pháp `"P-0042"` nhưng không tồn tại trong database; đây là **quy tắc nghiệp vụ**, không nhất thiết nên đi vào `PropertyEditor`. Editor nên chịu trách nhiệm parsing/formatting của representation, để validator/service xử lý tồn tại, quyền dùng hoặc trạng thái dữ liệu.

### Nếu text sai định dạng

```java
var editor = new PropertyEditorStateDemo.ProductCodeEditor();
try {
    editor.setAsText("wrong");
} catch (IllegalArgumentException ex) {
    System.out.println("Invalid code");
}
```

Output:

```text
Invalid code
```

Đây là đoạn minh họa dùng class ví dụ mục 3. Do `setAsText` ném exception **trước** `setValue`, state cũ sẽ giữ nguyên nếu editor đã có value trước đó. Khi binder gặp conversion exception, cách thông báo lỗi và quyết định không gán thuộc về binder; tránh tiếp tục dùng giá trị cũ của một editor tự tái sử dụng sau khi parse thất bại.

## 8. So sánh với `Converter` và `Formatter` của Spring

Spring cung cấp conversion API không đòi hỏi value mutable nội bộ:

```java
import org.springframework.core.convert.converter.Converter;

public class ProductCodeConverter implements Converter<String, ProductCode> {
    @Override
    public ProductCode convert(String source) {
        String normalized = source.trim().toUpperCase();
        if (!normalized.matches("P-[0-9]{4}")) {
            throw new IllegalArgumentException("Invalid code");
        }
        return new ProductCode(normalized);
    }
}
```

Đây là class minh họa với `ProductCode` đã được định nghĩa/import ở mục 3, không độc lập nếu đứng riêng. `Converter<String, ProductCode>` có hàm `convert` trả giá trị trực tiếp, không giữ “current value” bằng `setValue/getValue`. Do đó converter stateless thường có thể dùng chung an toàn hơn nếu implementation không lưu state khác.

`Formatter<T>` có `parse(String, Locale)` và `print(T, Locale)` để xử lý representation phụ thuộc locale (ví dụ date, money). Với code mới, cân nhắc `Converter` hoặc `Formatter` thay cho editor mutable; nhưng `PropertyEditor` vẫn xuất hiện trong JavaBeans và Spring binding, nhất là code kế thừa.

## 9. Các lỗi thường gặp

- **Coi `setAsText` là hàm trả object:** nó trả `void`, phải lấy kết quả qua `getValue()`.
- **Cho rằng `getAsText` trả nguyên văn input:** implementation có thể normalize, trim hoặc format lại value.
- **Quên gọi `setValue` trong custom `setAsText`:** editor không cập nhật state sau parse, binder có thể nhận null/giá trị cũ.
- **Dùng `getAsText` khi chưa có value:** code ép kiểu vô điều kiện có thể gây `NullPointerException`; cần xử lý null.
- **Dùng cùng một editor mutable cho nhiều request:** nguy cơ trộn state và race condition.
- **Nuốt lỗi parse nhưng giữ value cũ:** caller có thể tưởng dữ liệu mới đã được nhận; nên ném exception rõ và không dựa vào editor cũ.
- **Gán type khác vào `setValue`:** `PropertyEditorSupport` nhận `Object`; custom `getAsText` có cast có thể lỗi khi value không đúng kiểu.
- **Nhầm lỗi chuyển đổi với validation:** đúng syntax không bảo đảm dữ liệu hợp lệ về nghiệp vụ.
- **Viết editor quá nhiều trách nhiệm:** truy vấn database hoặc gọi dịch vụ bên ngoài trong parsing khiến binding khó kiểm thử và khó quản lý hiệu năng.

## 10. Checklist thiết kế và kiểm thử

1. Định nghĩa rõ chuỗi hợp lệ, cách normalize và cách xử lý null/blank.
2. Trong `setAsText`, parse xong phải cập nhật state bằng `setValue`.
3. Trong `getAsText`, đọc `getValue()` và xuất representation ổn định.
4. Thử `setAsText` thành công, thất bại, null, và thử `setValue` trực tiếp.
5. Xác định `getAsText` có chuẩn hóa input hay không; không yêu cầu round-trip giữ từng ký tự nếu không phải contract.
6. Không chia sẻ instance editor có state không được đồng bộ giữa nhiều luồng xử lý.
7. Khi tích hợp Spring, đăng ký editor trước `bind` và xác minh `BindingResult`.
8. Ưu tiên `Converter`/`Formatter` khi cần conversion thuần hoặc locale-aware.

**Ghi nhớ:** `setAsText` chuyển chuỗi thành giá trị và lưu vào trạng thái bên trong editor; `getAsText` đọc trạng thái ấy để xuất ra chuỗi. Hiểu rõ tính mutable giúp tránh dùng lại sai editor, phát hiện lỗi parse và cấu hình Spring data binding an toàn, nhất quán.
