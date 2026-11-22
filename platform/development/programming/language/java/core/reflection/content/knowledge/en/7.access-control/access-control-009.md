# Không xem `setAccessible` là bảo đảm sửa được mọi field trong Java Reflection

## 1. Vấn đề: mở kiểm tra truy cập khác với có quyền ghi

Trong Java Reflection, ta có thể nhận được đối tượng `Field` đại diện cho một trường, kể cả trường `private`, qua `getDeclaredField(...)`. Sau đó, `setAccessible(true)` yêu cầu Reflection **bỏ qua một số kiểm tra quyền truy cập của ngôn ngữ Java** khi đọc/ghi trường đó. Điều này **không phải** cam kết rằng `Field.set(...)` sẽ luôn thành công.

Có ít nhất bốn câu hỏi khác nhau:

1. **Tìm được field không?** `getField` chỉ tra cứu thành viên public phù hợp, còn `getDeclaredField` tìm thành viên trực tiếp được khai báo bất kể visibility; không có nghĩa thao tác truy cập hợp lệ.
2. **Có thể tắt kiểm tra truy cập không?** `setAccessible(true)` có thể thành công hoặc bị chặn bởi ranh giới module/runtime. `trySetAccessible()` cho biết thành công bằng kết quả boolean trong trường hợp thường gặp.
3. **Field có được phép ghi không?** `static final`, field `final` trong record và field `final` trong hidden class là những trường không thể đổi bằng `Field.set` dù thao tác mở quyền đã thành công.
4. **Lời gọi ghi có hợp lệ không?** Đối tượng đích, kiểu giá trị, quy tắc chuyển đổi primitive và trạng thái khởi tạo lớp phải phù hợp. Khi một kiểm tra không đạt, API có thể ném exception.

Sự khác nhau này quan trọng với mapper, framework dependency injection, serializer, công cụ migration, unit test và mọi đoạn mã định “sửa field private bằng Reflection”. Hãy luôn xử lý kết quả mở quyền và kết quả ghi như **hai bước độc lập**.

## 2. `setAccessible`, `trySetAccessible` và `canAccess` thực sự nói gì?

| API | Kết quả có ý nghĩa | Điều **không** được suy ra |
| --- | --- | --- |
| `field.setAccessible(true)` | Yêu cầu Reflection bỏ qua kiểm tra truy cập theo phạm vi runtime cho phép; nếu không thể, có thể ném `InaccessibleObjectException`. | Field chắc chắn ghi được hoặc toàn bộ module đã mở. |
| `field.trySetAccessible()` | Trả `true` khi đã bật được quyền bỏ qua kiểm tra; thường trả `false` khi không thể mở do module. Có thể ném `SecurityException` nếu bị từ chối theo cơ chế security áp dụng. | `Field.set` chắc chắn thành công. |
| `field.canAccess(target)` | Kiểm tra liệu **caller tại thời điểm gọi** có thể truy cập phản xạ trên target hợp lệ theo trạng thái hiện tại không. | Field có thể sửa; không thay thế kiểm tra `final`, target và giá trị. |
| `field.get(target)` | Đọc được giá trị khi thỏa điều kiện truy cập và target. | Việc đọc được giá trị đồng nghĩa có quyền ghi. |
| `field.set(target, value)` | Yêu cầu cập nhật giá trị; chỉ thành công khi mọi điều kiện về quyền, tính ghi được và kiểu đều thỏa. | Chỉ cần gọi `setAccessible(true)` trước là đủ. |

`setAccessible(false)` bật lại việc thực thi kiểm tra truy cập cho đối tượng Reflection đó; lời gọi `setAccessible(true)` không sửa modifier của field trong class file, không đổi định nghĩa module và không phá vỡ mọi giới hạn của JVM.

**Một lưu ý thuật ngữ:** “accessible flag” trên đối tượng `Field` biểu thị việc bỏ qua kiểm tra truy cập bằng Reflection. Nó khác với modifier `public`/`private`/`protected`, và hoàn toàn khác với modifier `final`. `canAccess` là phép kiểm tra quyền truy cập trong hoàn cảnh cụ thể, không phải API dự báo khả năng ghi.

## 3. Quyền mở reflection chịu ràng buộc của Java Platform Module System

Từ Java 9, ranh giới module có ý nghĩa đối với deep reflection. Với caller nằm trong class `C` muốn bật quyền truy cập thành viên thuộc class `D`, API nêu những trường hợp có thể bật, trong đó có:

- `C` và `D` thuộc **cùng module**.
- Thành viên và `D` đều `public`; package của `D` được **exports** đến module gọi.
- Thành viên `protected static` trong `D` public; package được exports và `C` là subclass của `D`.
- Package của `D` được **opens** đến module gọi; các package thuộc unnamed module hoặc open module được mở theo ngữ nghĩa tương ứng.

Đối với private, package-private hoặc protected instance member ở **module khác**, `exports` đơn thuần không cấp deep reflection; cần package được `opens` phù hợp. Nếu không, `setAccessible(true)` có thể ném `InaccessibleObjectException` và `trySetAccessible()` thường trả `false`. Các quy tắc chính xác phụ thuộc caller, loại thành viên, vị trí class và cách mở module.

Ví dụ minh họa trong `module-info.java` của module sở hữu model (mảnh cấu hình, không phải chương trình Java độc lập):

~~~java
module app.domain {
    exports app.domain.model;          // Cho truy cập API public.
    opens app.domain.model to app.mapper; // Cho app.mapper deep reflection.
}
~~~

`exports` và `opens` có mục đích khác nhau. Một chương trình trên classpath (unnamed module) chỉ muốn mở package cụ thể cho hoạt động kiểm thử có thể chạy với tùy chọn VM có phạm vi rõ ràng, ví dụ:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -cp out ReflectiveWriteDemo
~~~

Tùy chọn trên mở việc phản xạ vào `java.lang` cho unnamed modules và có thể khiến `trySetAccessible` của một field private bên trong `java.lang.String` trả `true`, nhưng **không** tạo quyền ghi vào field `final` vốn bị cấm sửa. Hãy hạn chế `--add-opens` cho nhu cầu hợp lệ, ưu tiên cấu hình mở package ở module sở hữu mã; tránh mở rộng toàn bộ module chỉ để thử vận may.

## 4. Trường nào vẫn không thể sửa dù mở quyền thành công?

Javadoc Java 17 định nghĩa nhóm **non-modifiable final fields** mà `setAccessible(true)` chỉ có thể hỗ trợ đọc, không tạo write access:

| Dạng field | Mở truy cập (khi được phép) | `Field.set(...)` |
| --- | --- | --- |
| Field instance bình thường, không `final` | Có thể bật | Có thể ghi nếu target và value hợp lệ. |
| Field `private final` instance của class thường | Có thể bật nếu module cho phép | Trong Java 17, API có thể cho ghi nếu các điều kiện đặc biệt được đáp ứng, nhưng không nên dựa vào kết quả dùng được sau đó. |
| Field `static final` của bất kỳ class/interface | Có thể bật để đọc | **Không có write access** qua `Field.set`. |
| Field `final` do record khai báo | Có thể bật để đọc | **Không có write access** qua `Field.set`. |
| Field `final` trong hidden class | Có thể bật để đọc | **Không có write access** qua `Field.set`. |
| Field private thuộc package không mở ở module khác | Có thể không bật được | Không thể bỏ qua module boundary bằng cách chỉ gọi `setAccessible`. |

Không nhầm `static` với `static final`: field `static` **không final** vẫn có thể thay đổi nếu quy tắc quyền và kiểu cho phép; khi gọi `Field.set` với static field, tham số target không dùng đến và có thể truyền `null`.

**Rủi ro của instance `final` trong class thường:** Theo hợp đồng `Field.set` của Java 17, việc sửa qua Reflection chỉ có ý nghĩa trong một số quy trình khôi phục/deserialization được kiểm soát trước khi đối tượng được công bố. Các lần đọc khác có thể vẫn quan sát giá trị cũ do giả định/optimization dựa vào `final`. Không dùng việc thấy một lần ghi thành công làm bằng chứng invariants của đối tượng đã được cập nhật an toàn. Hành vi và hạn chế với `final` cũng có thể khác ở phiên bản JDK mới; kiểm tra tài liệu của phiên bản thực tế.

## 5. Ví dụ Java 17+ chạy được: bật quyền thành công nhưng ghi thất bại

Chương trình sau tách riêng bước mở quyền, ghi và báo lỗi. Nó kiểm tra field mutable bình thường, `static final`, record component, sai kiểu giá trị và giới hạn module của JDK.

Lưu vào `ReflectiveWriteDemo.java`:

~~~java
import java.lang.reflect.Field;

public class ReflectiveWriteDemo {

    static class MutableModel {
        private String name = "old";
        private int count = 1;
        private static final String CATEGORY = "fixed";
    }

    record Snapshot(String code) {}

    static void attempt(String label, Field field,
                        Object target, Object newValue)
            throws ReflectiveOperationException {
        boolean opened = field.trySetAccessible();
        System.out.println(label + " | opened=" + opened);
        if (!opened) {
            System.out.println(label + " | write=SKIPPED");
            return;
        }

        try {
            field.set(target, newValue);
            System.out.println(label + " | write=OK");
        } catch (IllegalAccessException | IllegalArgumentException ex) {
            System.out.println(label + " | write="
                    + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        MutableModel model = new MutableModel();
        attempt("mutable private",
                MutableModel.class.getDeclaredField("name"),
                model, "updated");
        attempt("static final",
                MutableModel.class.getDeclaredField("CATEGORY"),
                null, "other");
        attempt("record final",
                Snapshot.class.getDeclaredField("code"),
                new Snapshot("original"), "other");
        attempt("wrong value type",
                MutableModel.class.getDeclaredField("count"),
                model, "not a number");

        Field jdkPrivate = String.class.getDeclaredField("value");
        System.out.println("JDK private | opened="
                + jdkPrivate.trySetAccessible());
    }
}
~~~

Biên dịch và chạy trên Java 17+ trong cấu hình JDK thông thường, không dùng `--add-opens`:

~~~bash
javac -encoding UTF-8 ReflectiveWriteDemo.java
java ReflectiveWriteDemo
~~~

Đầu ra trên JDK 17 hoặc 21 với `java.base/java.lang` chưa được mở cho unnamed module:

~~~text
mutable private | opened=true
mutable private | write=OK
static final | opened=true
static final | write=IllegalAccessException
record final | opened=true
record final | write=IllegalAccessException
wrong value type | opened=true
wrong value type | write=IllegalArgumentException
JDK private | opened=false
~~~

Giải thích từng trường hợp:

- `mutable private`: field private của model trong cùng unnamed module cho phép bật bỏ qua access check; target đúng kiểu và giá trị `String` hợp lệ nên ghi được.
- `static final`: mở quyền trả `true`, nhưng `CATEGORY` là field không được sửa. `Field.set(null, ...)` ném `IllegalAccessException`.
- `record final`: `Snapshot.code` do record khai báo là field final không được sửa; cũng thất bại với `IllegalAccessException`.
- `wrong value type`: `count` là `int`. Truyền `String` không được unbox/widen thành `int`; `Field.set` ném `IllegalArgumentException` dù đã mở quyền.
- `JDK private`: `String.value` là field implementation private trong module `java.base`. Trong cấu hình JDK nêu trên, package `java.lang` không mở cho chương trình, nên `trySetAccessible()` trả `false`. Chạy với `--add-opens` tương ứng có thể thay đổi dòng này; ví dụ chỉ minh họa trạng thái mặc định, không viết mã phụ thuộc cấu trúc nội bộ `String`.

Việc lấy `Field` ở đây thành công không chứng minh rằng thao tác đọc hoặc ghi sẽ được phép. Kết quả cụ thể của một field nội bộ JDK phụ thuộc cả phiên bản JVM và cờ dòng lệnh, vì vậy không nên dựa vào những chi tiết đó trong ứng dụng.

## 6. Vì sao `Field.set` còn có thể thất bại?

Sau khi đã bật truy cập, `Field.set(target, value)` vẫn phải tuân các điều kiện của Javadoc:

1. **Sai đối tượng đích:** Với field instance, `target == null` gây `NullPointerException`. Nếu target không là instance của lớp khai báo field (hoặc subtype tương thích), có thể ném `IllegalArgumentException`. Với field static, target được bỏ qua.
2. **Sai kiểu dữ liệu:** Java Reflection cho phép các chuyển đổi tự động có giới hạn: unboxing và widening primitive hợp lệ, không ép kiểu thu hẹp tùy ý; ví dụ truyền `Long` vào field `int` không phải conversion widening. Cần tránh giả định nó hoạt động như converter của JSON mapper.
3. **Chưa có quyền truy cập:** Nếu checks còn được thực thi và field không thể truy cập, `Field.set` có thể ném `IllegalAccessException`. `trySetAccessible()==false` cần được xử lý trước khi gọi.
4. **Field không có write access:** Nhóm non-modifiable final đã nêu khiến `Field.set` ném `IllegalAccessException` dù accessible flag có thể là `true`.
5. **Khởi tạo class static:** Ghi static field có thể kích hoạt class initialization; lỗi khởi tạo có thể dẫn đến `ExceptionInInitializerError`.
6. **Chính sách runtime/security:** `setAccessible(true)` có thể ném `InaccessibleObjectException`; nếu có cơ chế `SecurityManager` và quyền bị từ chối, `SecurityException` cũng có thể phát sinh. Không bắt `Exception` chung rồi coi đó là lỗi field không tồn tại.

Cần phân biệt lỗi **tìm metadata** (`NoSuchFieldException`), lỗi **bật truy cập** (`InaccessibleObjectException` hoặc `SecurityException`), lỗi **không được ghi** (`IllegalAccessException`) và lỗi **tham số** (`IllegalArgumentException` / `NullPointerException`). Mỗi loại báo một nguyên nhân khác nhau.

## 7. Quy trình triển khai an toàn cho công cụ dùng Reflection

Khi một công cụ buộc phải sửa field, nên biến những quyết định ẩn thành điều kiện tường minh:

1. **Ưu tiên API bình thường:** constructor, builder, setter, factory, phương thức nghiệp vụ hoặc tạo object mới. Với record, tạo record mới thay vì cố gắng thay field cũ.
2. **Chọn đúng field:** chỉ ra `declaringClass`, `name`, `type`; dùng `getDeclaredField` khi cần tìm field private trực tiếp; khi duyệt lớp cha cần chính sách rõ để xử lý field trùng tên. Không chọn ngẫu nhiên theo tên duy nhất.
3. **Kiểm tra modifier và cấu trúc:** `Modifier.isFinal(field.getModifiers())`, `Modifier.isStatic(...)`, `field.getDeclaringClass().isRecord()` và phạm vi model. Nếu nghiệp vụ không hỗ trợ `final`, từ chối sớm; đừng dựa vào việc thử ghi.
4. **Kiểm tra ngữ cảnh module:** nếu cần deep reflection, yêu cầu package mở đúng module; không mặc định caller được quyền. Dùng `trySetAccessible` và kiểm tra boolean, hoặc bắt lỗi từ `setAccessible(true)`.
5. **Kiểm tra target/value:** field instance có target phù hợp; static field không cần target; xác định conversion đúng thay vì thử ép tùy tiện.
6. **Ghi trong phạm vi được kiểm soát:** bắt các exception có ý nghĩa, trả thông báo chỉ ra `class.field` và nguyên nhân. Không tự fallback qua `Unsafe`, JNI hay hack modifier để cố viết vào field bị cấm.
7. **Kiểm tra kết quả theo hợp đồng nghiệp vụ:** có thể đọc lại field mutable trong trường hợp phù hợp, nhưng đừng dựa trên đọc lại Reflection để khẳng định việc sửa `final` có hiệu lực với mọi luồng hay mọi code đã biên dịch.

Một hàm tiện ích có thể diễn đạt chính sách cấm ghi vào field final ngay từ đầu, tránh xem `trySetAccessible` là phép thử quyền ghi:

~~~java
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;

static void setMutableField(Field field, Object target, Object value)
        throws IllegalAccessException {
    if (Modifier.isFinal(field.getModifiers())) {
        throw new IllegalArgumentException("Refuse final field: "
                + field.getDeclaringClass().getName() + "."
                + field.getName());
    }
    if (!field.trySetAccessible()) {
        throw new IllegalAccessException("Cannot open field: "
                + field.getDeclaringClass().getName() + "."
                + field.getName());
    }
    field.set(target, value);
}
~~~

Đây là **đoạn minh họa** để đặt trong một class thích hợp, không phải source độc lập thứ hai. Ngay cả khi từ chối `final` và đã bật access, `Field.set` vẫn có thể thất bại nếu target/value sai hoặc runtime có điều kiện khác. Nếu công cụ muốn tránh phản xạ private, chỉ hỗ trợ field public hoặc yêu cầu API setter trong module sở hữu model sẽ dễ kiểm chứng hơn.

## 8. Những hiểu nhầm phổ biến và cách sửa

| Nhận định dễ nhầm | Cách hiểu đúng |
| --- | --- |
| “Lấy được `getDeclaredField` là sửa được field.” | Tra cứu metadata không quyết định quyền đọc/ghi. |
| “`setAccessible(true)` luôn mở được private.” | Module/package/security có thể ngăn deep reflection. |
| “`trySetAccessible()==true` chứng minh `Field.set` thành công.” | Chỉ xác nhận trạng thái bỏ qua access check; tính ghi được và target/value vẫn cần kiểm tra. |
| “`final` chỉ là rào cản cú pháp.” | Có nhóm `final` hoàn toàn không có write access và các quy tắc về tính bất biến/bộ nhớ cần tôn trọng. |
| “Mở module bằng `--add-opens` thì sửa được `static final`.” | Mở truy cập không thay đổi quy tắc non-modifiable final. |
| “Đọc lại thấy giá trị mới tức hệ thống đã cập nhật an toàn.” | Đặc biệt với `final`, những đoạn code khác có thể tiếp tục quan sát giá trị cũ; nên dùng mô hình cập nhật object có hợp đồng rõ. |
| “Một lỗi trong `Field.set` nên bị bỏ qua im lặng.” | Phải phân biệt lỗi module, quyền ghi, target, kiểu và initialization để chẩn đoán đúng. |

## 9. Bài tập kiểm chứng

- Bỏ `trySetAccessible` ở ví dụ và thử `Field.set` vào `MutableModel.name` từ một class ở top-level không có quyền private; so sánh `IllegalAccessException`.
- Giữ `trySetAccessible` nhưng thay `newValue` cho `count` bằng `Integer.valueOf(5)`, dự đoán vì sao unboxing từ `Integer` sang `int` hợp lệ.
- Chạy demo với và không với `--add-opens java.base/java.lang=ALL-UNNAMED`; so sánh **chỉ khả năng mở truy cập** vào `String.value`, tránh thay đổi cấu trúc nội bộ của JDK.
- Viết constructor hoặc method `withCode(...)` trả về record `Snapshot` mới để cập nhật logic mà vẫn giữ tính bất biến.
- Tạo một ứng dụng nhiều module riêng và thực nghiệm sự khác nhau giữa `exports` và `opens` đối với truy cập `private`. Giữ phạm vi module mở càng hẹp càng tốt.

## 10. Nguồn tham khảo và nguyên tắc cần nhớ

- [Java SE 17 — `AccessibleObject`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): ý nghĩa accessible flag, quy tắc JPMS, `trySetAccessible`, nhóm non-modifiable final.
- [Java SE 17 — `Field`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html): điều kiện `Field.set`, lỗi target/type, ghi `final` và cảnh báo về kết quả quan sát.
- [dev.java — Reading and Writing Fields](https://dev.java/learn/api/reflection-method-handles/reflection/fields/): quy trình đọc/ghi field và lưu ý khi thao tác field final.

**Điểm cốt lõi:** `setAccessible` giải quyết **kiểm tra truy cập**, không đại diện cho **quyền ghi không giới hạn**. Mọi đường ghi Reflection cần xác minh ranh giới module, modifier, khả năng ghi thật sự, target, value và xử lý lỗi rõ ràng. Với các giá trị bất biến, việc thiết kế API cập nhật hợp lệ luôn an toàn hơn cố phá bất biến.
