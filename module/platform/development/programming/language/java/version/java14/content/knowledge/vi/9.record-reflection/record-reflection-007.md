# Phân biệt dữ liệu phản chiếu với hợp đồng công khai của thư viện khi làm việc với Java record

> **Phạm vi:** Java 14 – *Phản chiếu record*. Java 14 từng giới thiệu `record` dưới dạng preview; **record đã ổn định từ Java 16**, và API `java.lang.reflect.RecordComponent` là API chính thức từ Java 16. Bài dùng Java 17+ và API hiện hành, không sử dụng cú pháp preview hay các kỹ thuật phản chiếu cũ không phù hợp.

## 1. Hai khái niệm dễ bị nhầm

Một thư viện Java có thể xuất bản record:

~~~java
public record Invoice(String id, int amount) {}
~~~

Tại runtime, reflection có thể trả về tên component `id`, `amount`, kiểu, thứ tự khai báo, phương thức truy cập và annotation. Nhưng **việc một chi tiết nhìn thấy được bằng reflection không tự động biến chi tiết ấy thành hợp đồng mà thư viện cam kết duy trì cho người dùng**.

**Dữ liệu phản chiếu (reflection metadata)** mô tả cấu trúc được biên dịch và quan sát được của một kiểu **tại một phiên bản cụ thể**. Ví dụ: `Class.isRecord()`, `Class.getRecordComponents()`, `RecordComponent.getName()` và `RecordComponent.getAccessor()`.

**Hợp đồng công khai (public contract)** bao gồm những gì thư viện thực sự cho phép người tiêu dùng dựa vào: kiểu và phương thức public, constructor có thể gọi, tên/kiểu/thứ tự component nếu public record là phần API được xuất bản, hành vi được tài liệu hóa, bất biến dữ liệu, lỗi và chính sách tương thích giữa các phiên bản. Nếu thư viện có API JSON/REST/binary riêng, **schema truyền dữ liệu được công bố** là một phần hợp đồng khác cần quản lý.

Tách ba lớp này:

| Lớp | Ví dụ | Điều bảo đảm |
| --- | --- | --- |
| **Cấu trúc runtime** | Record có component `id` kiểu `String`, trả về bởi `getRecordComponents()` | Phản ánh cấu trúc class đang được nạp, theo các quy tắc của Java Reflection API |
| **Java API của thư viện** | `public Invoice(String id, int amount)`, `id()`, `amount()`, điều kiện `amount >= 0` được tài liệu hóa | Phụ thuộc công bố API và chính sách tương thích của thư viện; các thành viên public là bề mặt API |
| **Hợp đồng trao đổi dữ liệu** | Khóa JSON `"invoice_id"`, `"total_cents"`, quy tắc bắt buộc và phiên bản schema | Chỉ hình thành khi dịch vụ/serializer/tài liệu **quy định rõ**; reflection **không tự tạo ra hợp đồng này** |

Một framework có thể **dùng reflection để triển khai** hợp đồng công khai, nhưng dữ liệu quan sát được **không thay thế việc xác định** hợp đồng đó.

## 2. Reflection của record cung cấp những gì?

Các API ổn định và đang áp dụng:

| API | Giá trị trả về / ý nghĩa | Điểm cần nhớ |
| --- | --- | --- |
| `Class<?>.isRecord()` | `true` nếu class được khai báo là record | Kiểm tra trước khi duyệt components |
| `Class<?>.getRecordComponents()` | Mảng `RecordComponent[]`, theo **đúng thứ tự trong record header** | `null` khi class không phải record; mảng rỗng khi record không có component |
| `RecordComponent.getName()` | Tên component trong record header | Là tên Java ở class hiện tại; không mặc định là tên trường JSON |
| `RecordComponent.getType()` | Kiểu dưới dạng `Class<?>` | Với `List<String>` chỉ thấy `List.class` vì type erasure |
| `RecordComponent.getGenericType()` | Kiểu khai báo dưới dạng `Type` | Có thể giữ `List<String>` trong generic signature; không tự kiểm tra dữ liệu runtime |
| `RecordComponent.getAnnotatedType()` | Metadata về annotation trên vị trí sử dụng kiểu | Khác annotation của chính component declaration |
| `RecordComponent.getAccessor()` | `Method` tương ứng với accessor (ví dụ `id()`) | Method tồn tại trong metadata không đồng nghĩa mọi caller có quyền invoke |
| `RecordComponent.getAnnotations()` / `getAnnotation(...)` | Declaration annotations hiện diện ở runtime | Phụ thuộc `@Retention(RUNTIME)` và `@Target` phù hợp |
| `RecordComponent.getDeclaringRecord()` | Class record đã khai báo component | Giúp liên hệ component và kiểu chứa nó |

Các API nằm trong `java.lang` và `java.lang.reflect`; không cần thư viện bên thứ ba. `RecordComponent` mô tả một **component của record**, không phải là tên gọi khác của `java.lang.reflect.Field`.

### 2.1. Kiểm tra `null` đúng trước khi duyệt

~~~java
Class<?> type = String.class;

if (type.isRecord()) {
    for (var component : type.getRecordComponents()) {
        System.out.println(component.getName());
    }
}
~~~

Đây là **đoạn đặt trong phương thức**, không phải chương trình chạy độc lập. Với `String.class`, `isRecord()` là `false` và `getRecordComponents()` trả `null`. Với `record Empty() {}`, `isRecord()` là `true` nhưng mảng components có độ dài bằng `0`. Không đồng nhất **không phải record** với **record không có component**.

### 2.2. Thứ tự component là có bảo đảm; thứ tự field không phải vậy

`getRecordComponents()` trả các component **theo thứ tự được khai báo trong phần header**, giúp xác định thứ tự tham số canonical constructor. Nhưng `getDeclaredFields()` lấy các field do class khai báo và **không bảo đảm thứ tự**; nó cũng có thể gồm field static hay thành viên được sinh vì nhu cầu triển khai. Đừng suy luận các record components từ thứ tự `getDeclaredFields()` hay `getDeclaredMethods()`.

Record không cho khai báo thêm instance fields thông thường bên ngoài component fields, nhưng vẫn có static fields, methods, nested types... Các thành viên này có thể nhìn thấy qua các API reflection tương ứng mà **không phải components**.

### 2.3. Kiểu generic không đồng nghĩa xác thực dữ liệu

Với `List<String> tags`:

- `component.getType()` là `java.util.List.class`.
- `component.getGenericType().getTypeName()` có thể là `"java.util.List<java.lang.String>"`.
- JVM **không vì thế tự xác nhận** mọi phần tử trong list tại runtime là `String`; generic types trong Java chịu ảnh hưởng của *type erasure* và có thể bị phá vỡ bởi raw types/unchecked operations.

Reflection cho biết **kiểu đã khai báo**, không thay thế validate, kiểm tra null hay các bất biến nghiệp vụ.

## 3. Ví dụ hoàn chỉnh: đọc record metadata bằng Java 17+

Lưu với tên **`RecordReflectionDemo.java`**. Chương trình dùng nested public record để phương thức accessor có thể được gọi bằng reflection từ phạm vi hợp lệ, cùng một annotation do ta tự định nghĩa nhằm minh họa runtime metadata.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.RecordComponent;
import java.util.List;
import java.util.Objects;

public class RecordReflectionDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.RECORD_COMPONENT)
    public @interface WireName {
        String value();
    }

    public record Invoice(
            @WireName("invoice_id") String id,
            List<String> tags,
            int amount) {

        public Invoice {
            Objects.requireNonNull(id, "id");
            if (id.isBlank() || amount < 0) {
                throw new IllegalArgumentException("invalid invoice");
            }
            tags = List.copyOf(Objects.requireNonNull(tags, "tags"));
        }
    }

    public record Empty() {}

    public static void main(String[] args)
            throws ReflectiveOperationException {

        Class<Invoice> type = Invoice.class;
        System.out.println(type.isRecord());

        RecordComponent[] components = type.getRecordComponents();
        for (RecordComponent part : components) {
            System.out.println(
                    part.getName() + ":" + part.getType().getSimpleName()
                    + " | accessor=" + part.getAccessor().getName());
        }

        System.out.println(
                components[1].getGenericType().getTypeName());

        WireName annotation =
                components[0].getAnnotation(WireName.class);
        System.out.println(annotation.value());

        Invoice invoice = new Invoice("I-7", List.of("PAID"), 7);
        System.out.println(components[0].getAccessor().invoke(invoice));

        System.out.println(
                String.class.getRecordComponents() == null);
        System.out.println(
                Empty.class.getRecordComponents().length);
    }
}
~~~

Biên dịch/chạy từ JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 RecordReflectionDemo.java
java RecordReflectionDemo
~~~

**Stdout:**

~~~text
true
id:String | accessor=id
tags:List | accessor=tags
amount:int | accessor=amount
java.util.List<java.lang.String>
invoice_id
I-7
true
0
~~~

**Giải thích:**

1. `isRecord()` là `true` vì `Invoice` là record. Ba dòng component giữ **thứ tự header**: `id`, `tags`, `amount`.
2. `getType()` chỉ cho `List`, còn `getGenericType()` cho thấy phần tham số generic đã khai báo.
3. `@WireName("invoice_id")` là một **annotation minh họa** có `@Retention(RUNTIME)` và `@Target(RECORD_COMPONENT)`, nên `getAnnotation` có thể đọc nó.
4. `getAccessor()` trả `Method` của `id()`. `invoke(invoice)` gọi accessor và in `I-7`; ở ví dụ, class và accessor đều public và nằm trong phạm vi có thể truy cập.
5. `String` không phải record ⇒ `getRecordComponents() == null`. `Empty` là record rỗng ⇒ mảng trả về có độ dài 0.

**Không nhầm annotation với serializer:** `@WireName` chỉ là metadata do chương trình định nghĩa. Không có cơ chế mặc định của Java tự biến nó thành khóa JSON `invoice_id`, tự serialize, hoặc cam kết tương thích API. Một thư viện hoặc adapter **phải được viết và cấu hình để đọc annotation ấy** nếu muốn biến nó thành quy tắc xuất dữ liệu.

## 4. “Nhìn thấy qua reflection” khác “được public để dùng lâu dài”

### 4.1. Public Java API của record là những gì?

Khi thư viện xuất bản một `public record Invoice(String id, int amount)` trong một package có thể truy cập (đặc biệt nếu dùng Java Platform Module System, package cần được export phù hợp), Java cung cấp bề mặt API như:

- Chính kiểu `Invoice`, canonical constructor tương ứng; với public record, canonical constructor có mức truy cập public.
- Public accessor `id()`, `amount()`.
- Các phương thức `equals`, `hashCode`, `toString` theo hợp đồng record, trừ khi thư viện override hợp lệ.
- Những phương thức public bổ sung do thư viện khai báo.
- Bất biến và ý nghĩa dữ liệu được thư viện công bố, ví dụ đơn vị tiền là cent, không âm, `null` có được chấp nhận không.

Khi lập trình viên dựa vào `new Invoice("I-7", 700)` hoặc `invoice.amount()`, họ phụ thuộc vào **public Java API** thực sự, không chỉ vào reflection. Reflection có thể *nhận diện* cùng những phương thức đó nhưng không phải nguồn duy nhất định nghĩa hành vi công khai.

### 4.2. Một record nội bộ vẫn có metadata

~~~java
private record CacheEntry(String internalKey, long expiresAt) {}
~~~

Đây là **khai báo minh họa bên trong một lớp**. Từ mã trong lớp chứa nó, `CacheEntry.class.isRecord()` vẫn trả `true` và `getRecordComponents()` vẫn báo tên các component. Tuy nhiên, `CacheEntry` là **private**: thư viện không vì việc reflection có thể quan sát được mà phải xem `internalKey`, `expiresAt` là API công khai cho mọi người dùng.

Đặc biệt, `getDeclaredFields()` và `getDeclaredMethods()` là công cụ xem **các thành viên đã khai báo**, có thể gồm cả phần private hoặc do compiler tạo. Danh sách đó **không phải danh mục các thành viên mà người dùng thư viện được bảo đảm truy cập**.

### 4.3. Khi phản chiếu accessor vẫn bị chặn

`RecordComponent.getAccessor()` trả một `Method`, nhưng `Method.invoke(...)` phải qua kiểm tra truy cập của Java. Có thể gặp `IllegalAccessException` nếu record/class/method không truy cập được từ nơi gọi. Với hệ thống module, package không `exports` (hoặc không `opens` cho mục đích reflection sâu) cũng ảnh hưởng phạm vi truy cập.

Đừng dùng `setAccessible(true)` như giải pháp mặc định để “vượt qua” thiết kế API. Trên JDK hiện đại, strong encapsulation của module có thể ngăn việc đó bằng `InaccessibleObjectException`, và bỏ qua ranh giới truy cập làm code phụ thuộc chi tiết triển khai. Khi làm thư viện/framework, hãy thiết kế public accessor, package exports hoặc hợp đồng mở module một cách có chủ đích.

Nếu cần gọi accessor bằng reflection, xử lý lỗi truy cập và lỗi được chính accessor ném. `Method.invoke(...)` có thể bọc ngoại lệ từ phương thức đích trong `InvocationTargetException`; kiểm tra `getCause()` khi ghi log phù hợp thay vì đánh đồng mọi trường hợp với “không có component”.

## 5. Một bẫy thường gặp: tự suy ra JSON schema từ tên component

Giả sử thư viện có record:

~~~java
public record Invoice(String id, int amount) {}
~~~

Một mapper viết vội có thể đi qua `getRecordComponents()` rồi dùng `getName()` làm key để tạo đầu ra:

~~~text
{"id":"I-7","amount":700}
~~~

Đây là **ví dụ dữ liệu JSON minh họa**, không phải kết quả được Java tự sinh. Nếu API public đã công bố cấu trúc:

~~~text
{"invoice_id":"I-7","total_cents":700}
~~~

thì hai cấu trúc là **hai hợp đồng khác nhau**. Reflection trả chính xác tên Java `id`/`amount` nhưng **không biết** alias `invoice_id`, đơn vị cent, quy tắc bắt buộc, giá trị mặc định, chính sách bỏ qua `null`, hay phiên bản API.

Dùng reflection có thể thuận tiện khi làm framework, nhưng bạn vẫn phải quyết định rõ mapping, annotations có ý nghĩa gì, cách xử lý phiên bản cũ và cách kiểm tra compatibility.

### Ví dụ độc lập: adapter công khai có khóa cố định

Lưu mã dưới tên **`PublicContractDemo.java`**:

~~~java
import java.util.Map;
import java.util.Objects;

public class PublicContractDemo {

    // Kiểu nội bộ: metadata phản chiếu vẫn tồn tại,
    // nhưng bản thân kiểu private không là API public.
    private record InternalOrder(String id, int cents) {}

    public static Map<String, Object> toPublicFields(
            String id, int cents) {

        Objects.requireNonNull(id, "id");
        if (cents < 0) {
            throw new IllegalArgumentException("negative cents");
        }

        InternalOrder model = new InternalOrder(id, cents);

        // API đặt tên khóa có chủ đích, không lấy từ getName().
        return Map.of(
                "order_id", model.id(),
                "total_cents", model.cents());
    }

    public static void main(String[] args) {
        var fields = toPublicFields("T-9", 750);
        System.out.println(InternalOrder.class.isRecord());
        System.out.println(fields.get("order_id"));
        System.out.println(fields.get("total_cents"));
        System.out.println(fields.containsKey("id"));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 PublicContractDemo.java
java PublicContractDemo
~~~

~~~text
true
T-9
750
false
~~~

`InternalOrder` là private record nên vẫn có runtime metadata nhưng không là loại dữ liệu công khai được trả về. `toPublicFields` là một **phương thức public**, có hợp đồng trả về `Map<String,Object>`; trong ví dụ, mã adapter xác định hai khóa `order_id` và `total_cents`. Cần **tài liệu hóa những khóa này** nếu chúng là phần API mà client dựa vào. Việc thay đổi tên component `id` bên trong vẫn có thể thực hiện nếu adapter được cập nhật nhưng giữ nguyên khóa dữ liệu công khai.

`Map.of` trả map không thể chỉnh sửa và **không hứa hẹn thứ tự duyệt các khóa**; ví dụ lấy giá trị qua key, không in nguyên map như một định dạng chuẩn. Ví dụ cũng **không phải serializer JSON**: một HTTP/JSON API thật còn cần lớp serialize, quy tắc kiểu/null, kiểm tra schema và khả năng tương thích dữ liệu.

## 6. Phân biệt hợp đồng Java, metadata và quy tắc của framework

| Điều quan sát được | Có phải public contract không? | Quyết định nên dựa vào |
| --- | --- | --- |
| `getRecordComponents()` cho tên/thứ tự/kiểu của `public record` xuất bản | Thành phần header tác động trực tiếp đến Java API; có thể là ràng buộc compatibility | Tài liệu API, chữ ký constructor/accessor và chính sách versioning |
| `getRecordComponents()` của private/package-internal record | Không tự trở thành cam kết API public | Ranh giới truy cập và điều thư viện công bố |
| `getDeclaredFields()` trả một field private | Không tự động | Chi tiết triển khai; tránh phụ thuộc |
| `getAnnotation(WireName.class)` trả `invoice_id` | Chỉ trở thành contract nếu công cụ/tài liệu định nghĩa ý nghĩa annotation | Quy tắc xử lý annotation của framework |
| `getGenericType()` trả `List<String>` | Là thông tin kiểu **khai báo**; không bảo đảm dữ liệu runtime đã được kiểm tra | Hợp đồng kiểu, validation, compatibility |
| `getAccessor()` trả method `id()` | Method public có thể là API hợp lệ; còn gọi được hay không phụ thuộc truy cập | Mức truy cập class/method, exports, không dựa vào private reflection |
| Default `toString()` in tên component | Hữu ích cho debug; không tự biến thành định dạng wire | Dùng serializer/schema riêng khi giao tiếp |
| Thư viện cam kết `invoice_id` trong JSON | Có, nếu công bố là API | Test schema và versioning, kể cả khi model Java đổi tên |
| Mã phản chiếu thấy một field mới do compiler/tool thêm | Không nhất thiết là thay đổi API | Không dựa vào thứ tự/chi tiết không được hứa hẹn |

Vì vậy, câu “reflection cho biết kiểu hiện tại là gì” là **đúng nhưng chưa đủ** để kết luận “người dùng thư viện có thể dựa vào nó mãi mãi”.

## 7. Tương thích thư viện khi record thay đổi

Giả sử thư viện ban đầu công khai:

~~~java
public record Customer(String id, String name) {}
~~~

Một ứng dụng khách có thể dùng constructor `new Customer(id, name)`, accessor `id()/name()`, record equality và metadata thông qua `getRecordComponents()`.

| Thay đổi ở phiên bản thư viện | Metadata phản ánh gì? | Rủi ro đối với public contract |
| --- | --- | --- |
| Đổi tên `name` → `displayName` | `getName()` và accessor đổi | Caller dùng `name()` có thể hỏng; formatter dựa tên cũng đổi |
| Thêm `int tier` | Mảng components có thêm phần tử, canonical constructor đổi chữ ký | Mã gọi constructor cũ có thể không còn biên dịch/liên kết, trừ khi có overload duy trì |
| Đổi thứ tự `id` và `name` (cùng kiểu) | Thứ tự `getRecordComponents()` đổi | Chữ ký JVM có thể trùng do cùng kiểu, nhưng ngữ nghĩa positional constructor và cách ánh xạ có thể sai |
| Đổi `List<String>` → `List<Integer>` | `getType()` vẫn có thể là `List.class`, `getGenericType()` thay đổi | Hợp đồng generic, source compatibility và ý nghĩa dữ liệu đổi |
| Thêm/bỏ runtime annotation dùng bởi serializer | Annotation được phản chiếu đổi | Wire mapping có thể đổi nếu framework thực sự phụ thuộc annotation |
| Thay điều kiện validate trong canonical constructor | Metadata component có thể **không đổi** | Hành vi tạo đối tượng và lỗi nghiệp vụ đã đổi |
| Thêm private static helper | `getDeclaredMethods()` có thể đổi | Không nhất thiết ảnh hưởng public Java API |
| Thay cách render `toString()` | Có thể không đổi metadata component | Nếu client parse `toString`, client mong manh vì dựa vào biểu diễn debug |

**Kết luận kỹ thuật từ bảng:** Reflection không tự quyết định tương thích nguồn (*source compatibility*), tương thích nhị phân (*binary compatibility*), tương thích hành vi (*behavioral compatibility*) hay tương thích dữ liệu (*wire/schema compatibility*). Muốn kết luận phải kiểm tra **hợp đồng cụ thể** của từng lớp tiêu thụ.

Thay đổi tên component trong public record không phải “chỉ đổi metadata”: tên accessor cũng thay đổi. Ngược lại, thay đổi một field private trong một class không có bảo đảm riêng có thể chỉ là thay đổi triển khai. Đánh giá theo mức công khai và tài liệu được công bố, không theo khả năng “nhìn thấy” qua reflection.

## 8. Annotation và generic metadata cần được diễn giải cẩn thận

### 8.1. `@Target` quyết định vị trí, `@Retention` quyết định lúc đọc

Một annotation có thể được dùng ở vị trí record component, field, method, parameter hoặc type use **nếu khai báo `@Target` cho phép**. Với annotation:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface WireName {
    String value();
}
~~~

Đây là **đoạn khai báo**, cần import `java.lang.annotation.*`. `RecordComponent.getAnnotation(WireName.class)` có thể đọc annotation đó khi nó gắn trên component. Không suy ra rằng annotation cũng hiện trên field, accessor hay tham số constructor: mỗi vị trí phản chiếu có quy tắc target/propagation riêng. `getAnnotatedType()` phục vụ **type-use annotations**, phân biệt với declaration annotation trên chính component.

Nếu retention là `SOURCE` hoặc `CLASS`, đừng mong annotation xuất hiện qua reflection runtime như trên. Mọi hệ thống dựa trên annotation đều cần quy tắc xử lý tường minh và test đúng chỗ đọc.

### 8.2. Generic reflection không khôi phục được mọi thông tin

`getGenericType()` phản ánh khai báo kiểu, nhưng không thay thế việc kiểm tra dữ liệu tại runtime hoặc phân giải hết mọi kiểu trong một framework. Có thể gặp generic type variable, parameterized type và class loader khác nhau; một số trường hợp metadata signature hỏng hoặc thiếu class tham chiếu khiến việc đọc generic type thất bại.

Nếu xây mapper/công cụ tự động, cần quyết định xử lý `Type` một cách có hệ thống. Tránh chỉ ép mọi `Type` thành `Class<?>` hoặc tưởng `getType()` đã giữ mọi tham số generic. Nếu mục đích chỉ hiển thị metadata cho người học, tên kiểu và generic type name là đủ.

## 9. Thực hành an toàn với reflection trong thư viện

1. **Xác định đúng đối tượng công khai.** Không tự giả định mọi record phát hiện được đều là DTO public; một record private/internal vẫn có metadata.
2. **Kiểm tra `isRecord()`** hoặc kết quả null trước khi duyệt. Giữ thứ tự component như API cam kết, không dựa vào thứ tự field.
3. **Dùng public accessor cho giá trị** nếu phù hợp: `getAccessor()`, rồi chỉ gọi trong ngữ cảnh có quyền truy cập. Đừng mở private field chỉ để tiết kiệm thao tác.
4. **Ghi rõ schema và versioning.** Nếu API yêu cầu các khóa ổn định, ánh xạ tường minh hoặc sử dụng annotation/config do framework hỗ trợ và đã được kiểm thử.
5. **Không coi metadata là validation.** Constructor có thể kiểm tra đầu vào, accessor có thể có logic, một component generic vẫn không chứng minh dữ liệu runtime hợp lệ.
6. **Kiểm tra lỗi reflection.** Phân biệt class không phải record, loại không truy cập được, invocation thất bại, generic signature không thể phân giải và lỗi nghiệp vụ từ accessor.
7. **Giữ ranh giới module.** Không dùng mở sâu package/private members chỉ để thuận tiện; hợp đồng module `exports/opens` phải có chủ đích.
8. **Cân nhắc chi phí.** Công cụ gọi reflection nhiều lần có thể cache metadata `RecordComponent[]`/`Method` theo `Class<?>`, nhưng phải có chính sách phù hợp với class loader và không giữ class loader cũ sống mãi.
9. **Viết test theo hợp đồng công khai.** Dùng test API/wire, không chỉ test rằng `getRecordComponents()` trả đúng số phần tử.

### Một quy tắc hỗ trợ kiểm tra compatibility

Đối với thư viện Java công khai, ít nhất cần ba kiểu kiểm tra **theo nhu cầu thực**:

- **Test API Java**: một client biên dịch/gọi constructor và accessors được công bố, kiểm tra ngoại lệ và bất biến quan trọng.
- **Test metadata**: nếu thư viện **công bố** quy tắc reflection/annotation, xác nhận tên, thứ tự, kiểu và annotation mà consumer framework thực sự dùng.
- **Test dữ liệu ngoài**: nếu có JSON/REST/protocol, so sánh với schema đã chốt (tên khóa, kiểu, optional/required, null, dữ liệu mặc định và phiên bản).

Có thể chạy các kiểm tra này trên nhiều phiên bản thư viện/JDK mà dự án thực sự hỗ trợ. Không coi việc một chương trình “vẫn biên dịch” là bằng chứng duy nhất rằng client không bị đổi hành vi hoặc đổi định dạng dữ liệu.

## 10. Những lỗi hiểu sai phổ biến

| Nhận định sai | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| “`getRecordComponents()` thấy field nên đó là field public” | API trả `RecordComponent`, không phải `Field` | Record components có accessor và component fields riêng; access modifiers vẫn áp dụng |
| “`getDeclaredFields()` trả đúng thứ tự header” | Reflection không bảo đảm thứ tự field | Dùng `getRecordComponents()` để lấy thứ tự component |
| “Chỉ cần `@WireName` là JSON tự đổi key” | Java không tự triển khai serializer cho annotation tự định nghĩa | Framework/adapter phải được cấu hình để áp dụng |
| “`getType()` đủ cho `List<String>`” | Type erasure ẩn type arguments khỏi `Class<?>` | Dùng `getGenericType()` khi thật sự cần generic metadata |
| “`getGenericType()` chứng minh mọi phần tử đều là String” | Metadata phản ánh khai báo, không xác thực object graph runtime | Kiểm tra hợp đồng đầu vào và dữ liệu |
| “`getAccessor()` luôn invoke được” | Reflection vẫn phải tuân access control và module boundaries | Dùng public accessible API, xử lý lỗi truy cập |
| “Đọc được private component bằng reflection tức là API public” | Khả năng quan sát khác quyền sử dụng và cam kết compatibility | Dựa trên mức truy cập, exports, tài liệu |
| “Đổi tên component private/public đều vô hại” | Public record đổi cả accessor và metadata; constructor/semantics có thể đổi | Đánh giá versioning theo consumer và chữ ký |
| “`toString()` mặc định là schema JSON” | `toString()` để hiển thị, format không phải giao thức | Dùng serializer/schema công bố |
| “Không đổi metadata nghĩa là không đổi API” | Validate, exceptions, semantics có thể thay đổi mà metadata không đổi | Test behavioral contract |

## 11. Bài tập thực hành

1. Tạo `record Book(String isbn, String title)` và in `getRecordComponents()` theo thứ tự. Thử `String.class` và `record Empty() {}` để phân biệt null/mảng rỗng.
2. Đổi `List<String>` thành `List<Integer>` trong một record mẫu; so sánh `getType().getName()` và `getGenericType().getTypeName()`. Giải thích giới hạn type erasure.
3. Tạo annotation có `@Target(RECORD_COMPONENT)`, `@Retention(RUNTIME)`; đọc bằng `getAnnotation()`. Thử đổi retention để xem ảnh hưởng.
4. Tạo private nested record và gọi `isRecord()` từ lớp chứa. Giải thích vì sao nó không tự biến thành kiểu API public.
5. Giả sử API công bố khóa `invoice_id`, record nội bộ hiện dùng `id`. Viết adapter xuất dữ liệu và test tên khóa. Đổi tên component thành `reference`, nhưng giữ schema ngoài tương thích.
6. Thử sửa thứ tự hai components cùng kiểu `String`; xem khác biệt giữa thứ tự metadata và ý nghĩa tham số canonical constructor.
7. Viết bảng tác động của việc thêm component vào public record: chỗ nào cần kiểm tra lại về source/binary compatibility, annotation, schema và hành vi validate?
8. Tạo accessor tường minh cho một record; dùng `getAccessor()` rồi gọi method trong phạm vi có thể truy cập. Giải thích tại sao metadata không phải sự bảo đảm mọi caller có quyền gọi.

## 12. Nguồn chính thức để đối chiếu

- [Oracle Java SE 25 – Class.getRecordComponents](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html#getRecordComponents()): trả null nếu không là record; thứ tự component tương ứng record header.
- [Oracle Java SE 25 – RecordComponent](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/RecordComponent.html): `getType`, `getGenericType`, `getAccessor`, annotations và khai báo liên quan.
- [Oracle Java SE 25 – Record Classes](https://docs.oracle.com/en/java/javase/25/language/records.html): record ở mức ngôn ngữ và cách sử dụng.
- [Java SE 21 Language Specification `8.10 – Record Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10): hợp đồng component, constructor và accessors.
- [Oracle Java SE 25 – java.lang.reflect](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/package-summary.html): các API reflection chung.

**Ghi nhớ:** Reflection là **cách quan sát class đang có**, còn public contract là **lời hứa về điều client được phép dựa vào**. Với public record, các thành phần công khai là API có thật và có tác động tới compatibility; nhưng những chi tiết phản chiếu nội bộ, annotation tự tạo và tên component không tự động trở thành schema trao đổi dữ liệu. Thư viện tốt xác định, tài liệu hóa và kiểm thử các hợp đồng này riêng biệt.