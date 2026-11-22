# Không chia sẻ `PropertyEditor` có trạng thái giữa các luồng

## 1. Vấn đề cần giải quyết

Trong Spring Framework, `PropertyEditor` là cơ chế JavaBeans để chuyển giá trị văn bản sang kiểu thuộc tính và chuyển ngược lại. `DataBinder`/`WebDataBinder` và `BeanWrapper` có thể sử dụng các editor này khi gán dữ liệu vào đối tượng. Một editor thường **giữ giá trị đang xử lý trong chính instance của nó**: gọi `setAsText(...)` hoặc `setValue(...)` làm thay đổi trạng thái, sau đó `getValue()` hoặc `getAsText()` đọc trạng thái ấy.

Vì vậy, **không được chia sẻ cùng một instance editor có trạng thái cho nhiều luồng hoặc nhiều phiên binding có thể chạy xen kẽ**. Mỗi binder/lần sử dụng độc lập nên có editor riêng. Có thể tái sử dụng *cấu hình bất biến* hoặc *factory/registrar không giữ trạng thái*, miễn là chúng tạo editor mới khi đăng ký.

Hệ quả khi dùng chung editor không an toàn là giá trị của request A có thể bị request B ghi đè, khiến dữ liệu bị bind sai, lúc đúng lúc sai, hoặc trong trường hợp nhạy cảm gây lẫn dữ liệu giữa người dùng.

## 2. Vì sao `PropertyEditor` dễ gây race condition?

Giao diện `java.beans.PropertyEditor` có các thao tác phụ thuộc vào trạng thái hiện tại. `java.beans.PropertyEditorSupport` (lớp nền thông dụng) lưu giá trị qua `setValue(Object)` và trả lại qua `getValue()`. Một editor tùy biến thường viết:

```java
@Override
public void setAsText(String text) {
    setValue(parse(text)); // Thay đổi trạng thái của instance hiện tại
}
```

Đoạn trên **chỉ là phương thức minh họa**, cần có lớp editor và hàm `parse` cụ thể mới biên dịch được.

Nếu A và B cùng sử dụng đối tượng editor `E`, chuỗi thao tác sau có thể xảy ra:

| Thời điểm | Luồng A | Luồng B | Trạng thái bên trong E |
| --- | --- | --- | --- |
| 1 | `E.setAsText("Alice")` | | `"Alice"` |
| 2 | | `E.setAsText("Bob")` | `"Bob"` |
| 3 | `E.getValue()` → `"Bob"` | | `"Bob"` |

A đọc nhầm giá trị của B. Ngay cả khi từng phương thức hoạt động tốt khi chạy đơn luồng, một chuỗi *đặt giá trị rồi đọc giá trị* vẫn không phải thao tác nguyên tử. Ngoài `value`, editor có thể giữ bộ đệm, trạng thái parse hoặc một đối tượng như `SimpleDateFormat` (vốn cũng có trạng thái biến đổi). Không có bảo đảm an toàn luồng chung cho một instance `PropertyEditor` tùy biến.

**Phân biệt hai vấn đề:** Spring MVC thông thường tạo một `WebDataBinder` riêng cho mỗi request. Tuy nhiên, nếu nhiều binder khác nhau được đăng ký **cùng một đối tượng editor nằm trong field của singleton**, việc có binder riêng không còn cô lập trạng thái editor.

## 3. Ví dụ tái hiện lỗi, chỉ dùng JDK 17+

File `SharedEditorRaceDemo.java` sau **chạy độc lập**, không cần Spring. Hai `CountDownLatch` chủ động buộc A đọc sau khi B đã ghi, giúp minh họa lỗi một cách ổn định thay vì phụ thuộc may rủi vào bộ lập lịch.

```java
import java.beans.PropertyEditorSupport;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

public class SharedEditorRaceDemo {
    static final class NameEditor extends PropertyEditorSupport {
        @Override
        public void setAsText(String text) {
            setValue(text == null ? null : text.trim());
        }
    }

    static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(e);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        NameEditor shared = new NameEditor(); // Sai: cùng instance cho 2 luồng
        CountDownLatch aHasWritten = new CountDownLatch(1);
        CountDownLatch bHasWritten = new CountDownLatch(1);
        AtomicReference<Object> aRead = new AtomicReference<>();

        Thread a = new Thread(() -> {
            shared.setAsText("Alice");
            aHasWritten.countDown();
            await(bHasWritten);
            aRead.set(shared.getValue());
        });

        Thread b = new Thread(() -> {
            await(aHasWritten);
            shared.setAsText("Bob");
            bHasWritten.countDown();
        });

        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("A mong doi: Alice; thuc te: " + aRead.get());
        System.out.println("Gia tri cuoi cua editor: " + shared.getValue());
    }
}
```

Biên dịch và chạy:

```bash
javac SharedEditorRaceDemo.java
java SharedEditorRaceDemo
```

```text
A mong doi: Alice; thuc te: Bob
Gia tri cuoi cua editor: Bob
```

Kết quả cố định vì `CountDownLatch` thiết lập thứ tự A ghi → B ghi → A đọc. Trong ứng dụng thực, thứ tự xen kẽ không cố định, nên lỗi thường xuất hiện ngắt quãng và khó tái hiện. Ví dụ này chứng minh *mất tính cô lập của trạng thái*, không khẳng định mọi lần dùng chung editor đều tạo ra kết quả sai.

Thay `shared` bằng hai instance khác nhau (`editorA` và `editorB`), mỗi luồng đặt/đọc giá trị trên editor riêng, sẽ loại bỏ tương tác ghi đè cụ thể này. Để kiểm tra hệ thống Spring, cần xem cả **nơi tạo editor** và **nơi đăng ký editor**.

## 4. Anti-pattern trong Spring: giữ editor ở singleton

Mẫu sau là **đoạn minh họa sai, không phải chương trình độc lập**. Giả sử `TrackingCodeEditor` mở rộng `PropertyEditorSupport` và `TrackingCode` là kiểu thuộc tính cần bind:

```java
@ControllerAdvice
class UnsafeBindingAdvice {
    private final TrackingCodeEditor sharedEditor = new TrackingCodeEditor();

    @InitBinder
    void initBinder(WebDataBinder binder) {
        binder.registerCustomEditor(TrackingCode.class, sharedEditor);
    }
}
```

`@ControllerAdvice` thường là bean dùng chung; field `sharedEditor` sống theo bean. Mỗi lần `@InitBinder` chạy, các binder lại nhận **cùng tham chiếu**. Khi các request được xử lý đồng thời, các lần chuyển đổi có thể can thiệp vào nhau. Chuyển field sang `static`, đánh dấu `final` hoặc chỉ đặt `synchronized` trên riêng `setAsText` cũng không tự giải quyết được toàn bộ vấn đề: `final` chỉ cố định tham chiếu; còn thao tác đặt rồi đọc giá trị vẫn cần tính cô lập xuyên suốt.

Sai lầm tương tự có thể xuất hiện trong service singleton, cấu hình bean, registry tự xây hoặc cache giữ `PropertyEditor`. **Không lưu `PropertyEditor` đang mang giá trị vào scope rộng hơn phiên binding mà nó phục vụ.**

## 5. Cách đúng với `@InitBinder`: tạo editor mới

Trong Spring MVC, tạo và đăng ký editor **ngay trong lời gọi `@InitBinder`**. Ví dụ file `TrackingCodeBindingAdvice.java` dưới đây là một lớp Java 17 hợp lệ khi được đặt trong ứng dụng có dependency `spring-webmvc`; đây là lớp cấu hình MVC, **không phải chương trình có `main` để chạy riêng**.

```java
import java.beans.PropertyEditorSupport;
import java.util.Locale;

import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.InitBinder;

@ControllerAdvice
public class TrackingCodeBindingAdvice {

    public record TrackingCode(String value) {}

    public static final class TrackingCodeEditor
            extends PropertyEditorSupport {
        @Override
        public void setAsText(String text) {
            if (text == null || text.isBlank()) {
                throw new IllegalArgumentException("Tracking code is blank");
            }

            setValue(new TrackingCode(
                    text.trim().toUpperCase(Locale.ROOT)));
        }
    }

    @InitBinder
    public void initBinder(WebDataBinder binder) {
        // Mỗi lần khởi tạo binder nhận một editor mới.
        binder.registerCustomEditor(
                TrackingCode.class, new TrackingCodeEditor());
    }
}
```

Khi một thuộc tính có kiểu `TrackingCode` nhận chuỗi `" ab-12 "`, editor chuyển thành `new TrackingCode("AB-12")`. Editor của lần bind khác có trường `value` riêng. Lời gọi `registerCustomEditor(Class, PropertyEditor)` gắn **instance được truyền vào** với registry; chính người viết cấu hình chịu trách nhiệm cung cấp instance phù hợp.

Với ngày tháng dùng API cũ, nguyên tắc cũng vậy:

```java
@InitBinder
public void initBinder(WebDataBinder binder) {
    SimpleDateFormat format = new SimpleDateFormat("yyyy-MM-dd");
    format.setLenient(false);
    binder.registerCustomEditor(
            Date.class, new CustomDateEditor(format, false));
}
```

Đây là **đoạn phương thức minh họa**, cần các import `java.text.SimpleDateFormat`, `java.util.Date`, `org.springframework.beans.propertyeditors.CustomDateEditor` và các import MVC tương ứng. Mỗi lần gọi tạo **cả formatter lẫn editor mới**; không đưa `SimpleDateFormat` lên field dùng chung.

## 6. Tái sử dụng quy tắc đăng ký bằng `PropertyEditorRegistrar`

Khi cần cùng logic ở nhiều `DataBinder`, `BeanWrapper` hoặc khi Spring tạo bean, có thể chia sẻ một đối tượng **`PropertyEditorRegistrar` không có trạng thái**. Nó làm nhiệm vụ *tạo và đăng ký* editor mới cho registry nhận vào; nó không giữ lại editor để mọi registry dùng chung.

```java
import org.springframework.beans.PropertyEditorRegistrar;
import org.springframework.beans.PropertyEditorRegistry;

public final class TrackingCodeRegistrar
        implements PropertyEditorRegistrar {

    @Override
    public void registerCustomEditors(PropertyEditorRegistry registry) {
        registry.registerCustomEditor(
                TrackingCodeBindingAdvice.TrackingCode.class,
                new TrackingCodeBindingAdvice.TrackingCodeEditor());
    }
}
```

File `TrackingCodeRegistrar.java` này biên dịch được khi đặt cạnh `TrackingCodeBindingAdvice.java` ở cùng package và có dependency Spring Beans. Với một `DataBinder` được tạo thủ công, có thể gọi `registrar.registerCustomEditors(binder)` trong quá trình khởi tạo binder. Điều quan trọng: registrar có thể dùng lại, nhưng **`new ...Editor()` phải nằm trong `registerCustomEditors`**. Tài liệu Spring quy định registrar cần tạo editor mới cho mỗi lần đăng ký tương ứng, giúp tránh phải đồng bộ các editor dùng chung.

Nếu sử dụng API đăng ký custom editor cấp `BeanFactory` đời cũ, cần đọc đúng semantics của API đó: một số cơ chế có thể quản lý editor chia sẻ và đồng bộ nội bộ. Đừng suy từ việc framework có một cơ chế tương thích sang kết luận rằng editor tự viết có thể được chia sẻ tùy ý. Với cấu hình mới, ưu tiên registrar tạo instance mới.

## 7. Khi nào chọn `Converter` hoặc `Formatter`?

`PropertyEditor` là API JavaBeans có trạng thái. Với quy tắc chuyển đổi hiện đại, nên cân nhắc các abstraction của Spring:

| Trường hợp | Lựa chọn | Điều kiện an toàn luồng |
| --- | --- | --- |
| Tích hợp JavaBeans/legacy binder cần `PropertyEditor` | Editor tạo mới cho từng binder/registry | Không chia sẻ trạng thái `value` |
| Chuyển từ kiểu `S` sang `T` theo quy tắc chung | `Converter<S, T>` trong `ConversionService` | Implementation nên stateless hoặc tự bảo đảm thread-safe |
| Parse/format có `Locale` (ngày, số, tiền tệ...) | `Formatter<T>` / `FormattingConversionService` | Không giữ bộ parse mutable dùng chung; dùng API bất biến như `DateTimeFormatter` khi phù hợp |

Ví dụ converter stateless: `Converter<String, TrackingCode>` có phương thức `convert(String)` tạo `TrackingCode` trực tiếp từ input, không phải đi qua cặp `setValue/getValue`. Một converter/formatter **vẫn có thể không an toàn** nếu người viết tự đưa mutable state không đồng bộ vào field; tên interface không tự tạo ra thread safety.

Lưu ý `DateTimeFormatter` (thuộc `java.time`) bất biến và phù hợp để chia sẻ; `SimpleDateFormat` (thuộc `java.text`) có trạng thái mutable và không nên chia sẻ tự do giữa các luồng.

## 8. Kiểm tra và xử lý khi gặp lỗi

**Dấu hiệu đáng nghi** gồm kết quả parse lúc đúng lúc sai dưới tải đồng thời; giá trị một yêu cầu xuất hiện trong object của yêu cầu khác; lỗi khó tái hiện bằng test tuần tự; hoặc field editor bị lưu trong singleton/static/cache.

Để tìm gốc vấn đề:

1. Tìm các biến kiểu `PropertyEditor`/`PropertyEditorSupport` (đặc biệt field `static`, field `@ControllerAdvice`, `@Controller`, `@Component`, singleton bean và cache).
2. Tìm `registerCustomEditor(...)` và xác định instance truyền vào được tạo ngay tại đó hay lấy từ field dùng chung.
3. Nếu dùng `PropertyEditorRegistrar`, xác nhận `registerCustomEditors(...)` **tạo đối tượng editor mới trong mỗi lời gọi**.
4. Kiểm tra các dependency mutable được editor nắm giữ (ví dụ `SimpleDateFormat`, buffer, context theo request), kể cả khi chính editor mới được tạo.
5. Viết test nhiều tác vụ binding song song với input khác nhau; mỗi tác vụ nên dùng binder/target/editor riêng và khẳng định output ứng với **đúng input của tác vụ đó**. Kiểm thử đồng thời nhiều vòng để bắt trường hợp xen kẽ, nhưng vẫn dùng test có latch/barrier nếu cần tái hiện deterministically.
6. Xác minh không đưa editor hoặc target object dùng cho một request sang luồng khác sau khi bind khi chưa thiết kế vòng đời rõ ràng.

**Cách sửa ưu tiên:** chuyển tạo editor vào `@InitBinder`/registrar/factory per-binding; giữ logic và cấu hình bất biến ở đối tượng chia sẻ. Không dùng `ThreadLocal<PropertyEditor>` làm cách vá mặc định: thread pool tái sử dụng luồng, dữ liệu có thể còn sót giữa request và cần dọn dẹp chặt chẽ. Cũng không khóa một editor toàn cục chỉ để che race, vì dễ tạo nghẽn và yêu cầu toàn bộ chuỗi thao tác phải cùng tuân thủ một lock.

## 9. Tự kiểm tra hiểu bài

**Hỏi:** `@InitBinder` có chạy cho nhiều request, vậy phương thức đó có thread-safe không?

**Đáp:** Điểm quyết định là trạng thái mà nó truy cập. Phương thức dùng biến local và tạo editor mới cho binder thì không chia sẻ instance editor; phương thức lấy editor từ field chung lại tiềm ẩn race. `@InitBinder` tự nó không biến field mutable thành an toàn.

**Hỏi:** Chỉ gọi `setAsText` trong `synchronized` đã đủ?

**Đáp:** Chưa chắc. Nếu `getValue` diễn ra sau khi thả lock và luồng khác thay đổi giá trị, dữ liệu vẫn bị lẫn. Muốn đồng bộ phải bao trọn giao thức thao tác liên quan và mọi caller, điều khó bảo đảm trong framework; tách instance vẫn đơn giản và đúng vòng đời hơn.

**Hỏi:** Có thể dùng chung registrar không?

**Đáp:** Có, nếu registrar không giữ dữ liệu binding và tạo editor mới cho mỗi registry/lần đăng ký. Không giữ một `PropertyEditor` trong registrar rồi đăng ký cùng instance lặp lại.

**Quy tắc nhớ nhanh:** *Chia sẻ mô tả chuyển đổi, không chia sẻ đối tượng `PropertyEditor` đang lưu giá trị được chuyển đổi.*

## Tài liệu đối chiếu

- Spring Framework Reference — Validation, Data Binding, and Type Conversion: https://docs.spring.io/spring-framework/reference/core/validation.html
- Spring Framework Reference — Spring MVC `@InitBinder`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework Reference — MVC Data Binding (binder riêng theo request): https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html
- Spring Framework API — `PropertyEditorRegistry`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/PropertyEditorRegistry.html
