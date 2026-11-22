# Phân biệt `@Serial` với việc tự động thay đổi dữ liệu lúc chạy

> **Chủ đề:** Java 14 → *Annotation Serial* → **Phân biệt @Serial với việc tự động thay đổi dữ liệu lúc chạy**. Annotation `java.io.Serial` có từ **Java 14** và vẫn được hỗ trợ trong **Java SE 25**. Nó phục vụ **kiểm tra khai báo khi biên dịch**, không phải một bộ chuyển đổi dữ liệu runtime. Bài sử dụng ví dụ **Java 17+** và cơ chế Java Object Serialization hiện hành, không dựa vào API legacy hay tính năng preview.

## 1. Kết luận cốt lõi

**`@Serial` không tự động mã hóa, làm sạch, chuẩn hóa, lọc, ẩn, đổi kiểu, cập nhật hay thay đổi nội dung object khi ứng dụng chạy.** Nó không tự bật serialization và không làm một phương thức được gọi nếu phương thức ấy sai chữ ký mà giao thức serialization đòi hỏi.

Annotation có khai báo:

~~~java
@Target({ElementType.METHOD, ElementType.FIELD})
@Retention(RetentionPolicy.SOURCE)
public @interface Serial {
}
~~~

Đây là **dạng mô tả rút gọn** của định nghĩa chuẩn, không phải mã cần tự khai báo; trong chương trình hãy import `java.io.Serial` của JDK. Từ `@Retention(SOURCE)` rút ra một điểm quan trọng: **dấu `@Serial` được dùng ở mức mã nguồn/biên dịch, không được giữ làm annotation runtime để reflection tìm ra**.

**Bảng phân biệt nhanh:**

| Câu hỏi | `@Serial` tự làm? | Thành phần thực sự quyết định |
| --- | --- | --- |
| Đánh dấu khai báo nào có chủ đích tham gia Java serialization? | **Có**, cho compiler/tool phân tích mã nguồn | Annotation `@Serial` |
| Hỗ trợ cảnh báo sai tên/chữ ký/type của một số serialization members? | **Có thể**, tùy compiler và lint settings | Trình biên dịch kiểm tra khai báo, ví dụ `javac -Xlint:serial` |
| Làm class trở thành `Serializable`? | **Không** | `implements java.io.Serializable` hoặc cơ chế khác theo loại class |
| Quyết định trường nào được lưu mặc định? | **Không** | Quy tắc Java Serialization: non-static, non-transient; hoặc `serialPersistentFields` hợp lệ |
| Tự bỏ qua token/mật khẩu khi ghi object? | **Không** | Thiết kế field, `transient`, custom serialization, không đưa secrets vào stream |
| Tự gọi hay tự sinh `readObject`/`writeObject`? | **Không** | Những method thật có **đúng chữ ký** và giao thức `ObjectInputStream`/`ObjectOutputStream` |
| Tự chuẩn hóa chuỗi bằng `strip()` khi đọc? | **Không** | Mã lập trình viên viết trong `readObject` hoặc logic khác |
| Tự quyết định object thay thế khi serialize/deserialize? | **Không** | `writeReplace` / `readResolve` có chữ ký hợp lệ và kết quả thực thi |
| Tự tăng `serialVersionUID` khi lớp thay đổi? | **Không** | Giá trị field `serialVersionUID` hoặc cách tính UID mặc định của serialization |
| Bảo vệ ứng dụng khỏi deserialization của dữ liệu không đáng tin? | **Không** | Tránh deserialization không tin cậy, `ObjectInputFilter` và chính sách bảo mật |

**Nhận xét đúng:** `@Serial` giúp diễn đạt ý định và phát hiện một số lỗi **khi viết code**. Còn các thay đổi trong byte stream và object khi chạy do **giao thức cùng những khai báo/hàm thực sự có hiệu lực** quyết định.

## 2. Vì sao annotation này dễ bị hiểu nhầm?

Nhiều người quen với các annotation của framework có thể ảnh hưởng xử lý runtime, ví dụ annotation được framework tra cứu để chọn cách chuyển JSON. Thấy `@Serial` đặt trên `readObject` hoặc `serialVersionUID`, người học có thể cho rằng:

> “Nhờ thêm `@Serial`, JVM mới bắt đầu gọi hàm hoặc tự thay đổi dữ liệu.”

**Điều đó sai.** Java Object Serialization đã có quy tắc nhận diện **những tên, modifiers và signatures đặc biệt** từ trước. `@Serial` được thêm để người đọc và công cụ biên dịch biết rằng khai báo đó *được dự định* dùng trong cơ chế serialization.

Hình dung hai giai đoạn:

~~~text
GIAI ĐOẠN BIÊN DỊCH
    source code
      @Serial private void readObject(...)
        |
        +-- compiler có thể kiểm tra tên, kiểu, ngữ cảnh
        |
        +-- biên dịch ra class file
             (@Serial có retention SOURCE)

GIAI ĐOẠN CHẠY
    ObjectInputStream.readObject()
        |
        +-- giao thức tra cứu method thực sự hợp lệ
        +-- đọc field dữ liệu
        +-- gọi hook hợp lệ nếu class định nghĩa hook
        +-- chạy chính những câu lệnh do developer viết
        |
        +-- object được phục hồi / có thể được thay thế
             KHÔNG phải do presence của @Serial
~~~

Dù annotation được giữ trong source code để compiler kiểm tra, phần runtime **không đi tìm `@Serial` trên phương thức** rồi mới quyết định dùng phương thức ấy. Nếu bỏ annotation nhưng giữ nguyên phương thức, chữ ký và logic, hành vi Java serialization vẫn theo những khai báo đang có.

### So sánh với `@Override`

`@Override` giúp compiler kiểm tra ý định override, nhưng không phải chính nó tạo quan hệ override ở runtime. Tương tự, `@Serial` hỗ trợ kiểm tra ý định khai báo serialization member, nhưng **không phải chính annotation khởi động serialization hay thay đổi stream dữ liệu**.

Không được diễn giải phép so sánh này thành “mọi annotation Java đều chỉ phục vụ compiler”. **Có các annotation khác được giữ đến runtime và được framework xử lý.** Nhận định “không có runtime effect” ở đây áp dụng cho **`java.io.Serial`**, theo định nghĩa `RetentionPolicy.SOURCE` của chính annotation đó.

## 3. Những khai báo nào được `@Serial` hỗ trợ?

Theo Javadoc Java SE 25, có **hai field** và **năm method** liên quan đến cơ chế Java Object Serialization được dự định đánh dấu bằng `@Serial`.

### 3.1. Hai field đặc biệt

~~~java
@Serial
private static final long serialVersionUID = 1L;

@Serial
private static final ObjectStreamField[] serialPersistentFields = {
        new ObjectStreamField("name", String.class)
};
~~~

Đoạn này nằm **trong một lớp phù hợp có `implements Serializable`**, và cần import `java.io.Serial`, `java.io.ObjectStreamField`. Không nên chép hai field này vào mọi lớp mà không có nhu cầu.

- `serialVersionUID` xác định **UID phục vụ kiểm tra tính tương thích của lớp với stream**. Kiểu và modifiers có ý nghĩa thực sự là `private static final long`. `@Serial` không chọn giá trị `1L`, không tự tăng version.
- `serialPersistentFields` khai báo **bộ trường của serialized form** thay cho danh sách field mặc định khi dùng đúng cơ chế và thực hiện mapping thích hợp. Chính array `ObjectStreamField[]` cùng các method serialization mới có thể làm serialized form khác đi; annotation chỉ đánh dấu ý định.

**Phân biệt:** xóa riêng `@Serial` nhưng giữ nguyên giá trị `serialVersionUID` và trường `serialPersistentFields` hợp lệ **không tự đổi serialization protocol**. Ngược lại, chỉ đổi `serialVersionUID` từ `1L` thành `2L` có thể làm stream cũ không tương thích, **dù `@Serial` giữ nguyên**.

### 3.2. Năm method đặc biệt

| Method có chữ ký dự kiến | Vai trò khi runtime dùng đúng quy tắc | `@Serial` đóng vai trò gì? |
| --- | --- | --- |
| `private void writeObject(ObjectOutputStream out) throws IOException` | Ghi state tùy biến của lớp | Đánh dấu/kiểm tra khai báo, **không tự ghi dữ liệu** |
| `private void readObject(ObjectInputStream in) throws IOException, ClassNotFoundException` | Đọc state, có thể kiểm tra hay chuyển đổi dữ liệu | Đánh dấu/kiểm tra khai báo, **không tự gọi nếu sai signature** |
| `private void readObjectNoData() throws ObjectStreamException` | Xử lý tình huống không có dữ liệu cho lớp này khi khôi phục class hierarchy | Không tự tạo default values hoặc gọi method tùy ý |
| `Object writeReplace() throws ObjectStreamException` | Cho phép thay object được ghi ra stream bằng object khác | Không tự chọn object thay thế |
| `Object readResolve() throws ObjectStreamException` | Có thể trả object thay thế sau khi đọc | Không tự tạo singleton/đổi danh tính object |

Trong bảng, tên kiểu `ObjectOutputStream`/`ObjectInputStream`/`ObjectStreamException` thuộc `java.io`; bảng là **mẫu chữ ký**, không phải mọi method bắt buộc phải có ở một lớp. Với `writeReplace` và `readResolve`, Javadoc cho phép **nhiều mức access** theo quy tắc riêng thay vì chỉ `private`; đừng áp đặt quy tắc modifier của `writeObject` lên hai method ấy.

Ví dụ một method **thật** có xử lý dữ liệu:

~~~java
@Serial
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
    name = name.strip();
}
~~~

Đây là **đoạn method đặt trong class có field `String name`**, không phải file tự chạy. Việc bỏ khoảng trắng hai đầu xảy ra vì **câu lệnh `name = name.strip();` do lập trình viên viết**, **không phải** vì có `@Serial`. `in.defaultReadObject()` thực hiện khôi phục các field serialization mặc định trước khi logic tùy biến chạy.

**Sai chữ ký thì không được khắc phục chỉ bằng annotation.** Ví dụ `readObject(String text)` không phải serialization callback mà `ObjectInputStream` dự kiến; `@Serial` có thể giúp compiler cảnh báo sai lệch, nhưng nó **không đổi `String` thành `ObjectInputStream`** hoặc tạo ra một hook hợp lệ.

## 4. Cơ chế runtime thực sự làm gì?

### 4.1. Một lớp phải tham gia serialization theo quy tắc của Java

~~~java
import java.io.Serializable;
import java.io.Serial;

final class Invoice implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private String customer;
    private int amount;
    private transient String accessToken;
}
~~~

Đây là **một lớp minh họa có thể biên dịch**, không bao gồm main method. `implements Serializable` đánh dấu khả năng tham gia protocol Java serialization. Chỉ có `@Serial` trên một field hoặc method **không biến một class thông thường thành Serializable**.

Với default serialization của một lớp serializable thông thường:

- **Non-static, non-transient fields** được coi là phần serialized state theo quy tắc; `customer` và `amount` là ví dụ.
- **`transient` fields** bị bỏ qua khi lưu mặc định; `accessToken` **không được khôi phục từ stream** theo cơ chế mặc định.
- **Static fields** thuộc lớp, không phải state mỗi instance, nên không được ghi như instance fields trong default serialization.
- Sau khi deserialization, field `transient` chưa được khôi phục có giá trị mặc định của kiểu (ví dụ reference là `null`), trừ khi logic code gán lại.

**Đừng nghĩ `@Serial` tự quyết định ẩn thông tin nhạy cảm.** `transient` là một điều kiện của serialized form mặc định, không phải giải pháp bảo mật duy nhất: custom `writeObject` vẫn có thể cố tình ghi dữ liệu nhạy cảm vào stream, nên cần code review.

### 4.2. Điều gì làm dữ liệu thay đổi lúc đọc?

Nếu lớp có `readObject` **hợp lệ** và trong đó có:

~~~java
in.defaultReadObject();
name = name.strip();
~~~

thì object khi đọc có thể có `name` đã loại bỏ khoảng trắng. Có hai điều **khác nhau**:

1. Runtime nhận diện method theo **tên, chữ ký và quyền truy cập** được Java Serialization Specification định nghĩa.
2. Mã `name.strip()` thay đổi state sau khi phục hồi.

`@Serial` có thể xuất hiện trên method đó để compiler nhận biết ý định, **nhưng không tham gia vào hai thao tác runtime này**. Xóa annotation không xóa câu lệnh `strip()` và cũng không xóa method.

Ngược lại, nếu chỉ khai báo:

~~~java
@Serial
private static final long serialVersionUID = 1L;
~~~

thì không có câu lệnh nào nói rằng `name` phải được trim, chuyển thành chữ hoa, mã hóa hay gán lại. Kết quả round-trip của `name` không tự thay đổi chỉ vì field UID được annotate.

### 4.3. Tại sao `serialVersionUID` không phải bộ sửa dữ liệu?

`serialVersionUID` tham gia **kiểm tra sự tương thích** giữa class descriptor của stream và class runtime; khi không tương thích có thể xảy ra `InvalidClassException`. Nó **không** phải version migration engine:

- Không tự map tên field cũ sang tên mới.
- Không tự chuẩn hóa/cập nhật giá trị đã ghi.
- Không tự tạo `readObject` để vá schema.
- Không bảo đảm thay đổi cấu trúc lớp luôn backward-compatible.

Nếu cần thay đổi serialized form giữa các phiên bản, phải thiết kế tương thích theo Java Object Serialization Specification, sử dụng những hook/field đặc biệt khi phù hợp hoặc chọn format có schema/versioning rõ ràng. `@Serial` **chỉ cho compiler biết đây là một khai báo serialization-related**.

## 5. Ví dụ chạy đầy đủ: có và không có `@Serial` vẫn xử lý như nhau

Bài thực hành sau **không dùng tệp ngoài hoặc dữ liệu không đáng tin**. Nó serialize object vào `byte[]` trong memory rồi deserialize lại **những byte do chính chương trình tạo ra**. Mục tiêu là chứng minh một quan hệ nhân quả:

- Có `@Serial` trên `serialVersionUID` nhưng không có custom `readObject` → chuỗi `text` **không tự bị trim**; field `transient` thành `null`.
- Có `@Serial` trên `readObject` và code `strip()` → chuỗi bị trim vì code thực tế.
- **Bỏ `@Serial` trên `readObject` nhưng giữ đúng signature và cùng code `strip()`** → kết quả runtime **vẫn bị trim như trên**.
- Reflection không tìm thấy `@Serial` ở runtime vì retention là `SOURCE`.

**File duy nhất: `SerialBehaviorDemo.java`**

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serial;
import java.io.Serializable;

public class SerialBehaviorDemo {
    private static final class Plain implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;
        private final String text;
        private transient String token;

        Plain(String text, String token) {
            this.text = text;
            this.token = token;
        }
    }

    private static final class MarkedHook implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;
        private String text;

        MarkedHook(String text) {
            this.text = text;
        }

        @Serial
        private void readObject(ObjectInputStream in)
                throws IOException, ClassNotFoundException {
            in.defaultReadObject();
            text = text.strip();
        }
    }

    private static final class UnmarkedHook implements Serializable {
        private static final long serialVersionUID = 1L;
        private String text;

        UnmarkedHook(String text) {
            this.text = text;
        }

        // Có đúng chữ ký nhưng KHÔNG có @Serial.
        private void readObject(ObjectInputStream in)
                throws IOException, ClassNotFoundException {
            in.defaultReadObject();
            text = text.strip();
        }
    }

    private static Object roundTrip(Object value)
            throws IOException, ClassNotFoundException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();

        try (ObjectOutputStream out = new ObjectOutputStream(bytes)) {
            out.writeObject(value);
        }

        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(bytes.toByteArray()))) {
            return in.readObject();
        }
    }

    public static void main(String[] args) throws Exception {
        Plain plain = (Plain) roundTrip(
                new Plain("  An  ", "token"));

        MarkedHook marked = (MarkedHook) roundTrip(
                new MarkedHook("  An  "));

        UnmarkedHook unmarked = (UnmarkedHook) roundTrip(
                new UnmarkedHook("  An  "));

        System.out.println("plain=[" + plain.text + "]");
        System.out.println("transientToken=" + plain.token);
        System.out.println("markedHook=[" + marked.text + "]");
        System.out.println("unmarkedHook=[" + unmarked.text + "]");
        System.out.println("annotationVisibleAtRuntime=" +
                Plain.class.getDeclaredField("serialVersionUID")
                        .isAnnotationPresent(Serial.class));
    }
}
~~~

**Biên dịch và chạy với JDK 17 trở lên:**

~~~bash
javac --release 17 -encoding UTF-8 SerialBehaviorDemo.java
java SerialBehaviorDemo
~~~

**Stdout chính xác đã kiểm tra trên JDK 24:**

~~~text
plain=[  An  ]
transientToken=null
markedHook=[An]
unmarkedHook=[An]
annotationVisibleAtRuntime=false
~~~

### 5.1. Giải thích từng dòng kết quả

**`plain=[  An  ]`:** `Plain` có `@Serial` trên `serialVersionUID`, nhưng không có method nào chuyển đổi `text`. Giá trị chuỗi giữ nguyên **hai khoảng trắng ở mỗi đầu** sau round-trip.

**`transientToken=null`:** field `token` không được ghi bởi default serialization vì khai báo `transient`. Đây là cơ chế khác hoàn toàn với `@Serial`. Nếu bạn bỏ `transient` và không thay đổi gì khác, field có thể trở thành một phần serialized state mặc định (trừ khi class định nghĩa serialized form riêng).

**`markedHook=[An]`:** `MarkedHook` có `readObject` hợp lệ; sau `in.defaultReadObject()`, chương trình gọi `text.strip()`. Giá trị thành `An` là tác dụng của **method body**.

**`unmarkedHook=[An]`:** `UnmarkedHook` có **cùng kiểu method và logic**, chỉ không có `@Serial`. Runtime vẫn gọi hook và trim như vậy. Đây là bằng chứng trực tiếp rằng annotation **không phải công tắc thực thi**.

**`annotationVisibleAtRuntime=false`:** reflection đối với field đã có `@Serial` trong source **không nhìn thấy annotation này**, vì `java.io.Serial` có retention `SOURCE`. Điều đó không chứng minh method/field serialization không tồn tại — chỉ chứng minh annotation không được lưu để phản chiếu tại runtime.

### 5.2. Điều ví dụ KHÔNG chứng minh

- Hai class `MarkedHook` và `UnmarkedHook` **có tên khác nhau**, nên **không** suy ra hai byte streams của hai class khác nhau phải giống từng byte.
- Không suy ra mọi class `Serializable` đều nên viết custom `readObject`; mặc định thường đơn giản hơn nếu không có nhu cầu đặc biệt.
- Không dùng ví dụ này như công thức deserialize dữ liệu nhận từ mạng/người dùng: `ObjectInputStream` đọc dữ liệu không đáng tin có rủi ro bảo mật, cần tránh hoặc kiểm soát chặt.
- Không kết luận rằng dữ liệu Java serialization luôn phù hợp cho API public, JSON, thông điệp liên dịch vụ hoặc persisted schema lâu dài.

**Kết luận của phép thử là tương đương về hành vi xử lý `strip()`, không phải đồng nhất stream format cho hai tên class.**

## 6. Compiler giúp gì khi có `@Serial`?

Annotation này được thêm để hỗ trợ **kiểm tra khai báo** giống tinh thần `@Override`, đặc biệt vì Java serialization sử dụng một số **special methods** thường ít được gọi trực tiếp từ code. Nếu viết sai:

~~~java
import java.io.Serial;
import java.io.Serializable;

class BadSerialDeclaration implements Serializable {
    @Serial
    private static final int serialVersionUID = 1;

    @Serial
    private void readObject(String text) {
    }
}
~~~

Đây là **ví dụ cố ý sai**, **không nên sao chép vào production**. Có ít nhất hai vấn đề:

1. `serialVersionUID` phải có kiểu `long`, không phải `int`. Field sai kiểu không trở thành UID đặc biệt chỉ nhờ annotation.
2. `readObject(String)` không phải special `readObject(ObjectInputStream)`. Java serialization không sử dụng method này để khôi phục state, dù có `@Serial`.

Trên JDK 24, khi chạy:

~~~bash
javac --release 17 -Xlint:serial BadSerialDeclaration.java
~~~

compiler báo **hai cảnh báo** về UID không phải kiểu `long` và tham số của `readObject` không phải `ObjectInputStream`. **Exit code của lần biên dịch thử là 0** — đây là cảnh báo, không phải lỗi bắt buộc chặn build. Câu chữ chẩn đoán và mức kiểm tra có thể khác theo JDK/compiler.

**Phân biệt ba điều:**

- Javadoc `@Serial` **khuyến khích** compiler xác minh xem annotation đặt đúng vào field/method và đúng ngữ cảnh hay không. Đừng bảo đảm mọi compiler sẽ phát hiện toàn bộ sai lầm.
- `-Xlint:serial` có thể giúp kiểm tra thêm các cảnh báo liên quan serialization, như class `Serializable` thiếu UID. Nó không phải công cụ kiểm thử runtime hay công cụ bảo mật.
- Nếu dự án yêu cầu lint không có warning, có thể kết hợp chính sách CI nghiêm (chẳng hạn `-Werror` theo công cụ đang dùng), nhưng trước hết cần đọc hiểu warning và sửa nguyên nhân chứ không tắt bừa.

**Quan trọng:** code sai ở trên vẫn có thể **biên dịch và chạy** với hành vi serialization mặc định; điều đó càng cho thấy `@Serial` **không tự làm runtime nhận diện những khai báo sai**.

## 7. Khi nào dữ liệu thực sự thay đổi? Bảng tác nhân

| Thay đổi trong source | Có thể thay đổi runtime/serialized form không? | Vì sao |
| --- | --- | --- |
| Thêm/bỏ riêng `@Serial` ở khai báo vốn hợp lệ | **Không**, tự thân annotation không thay đổi protocol | `SOURCE` retention, compiler-level intent |
| Thêm `implements Serializable` vào class phù hợp | **Có** | Class tham gia Java serialization protocol |
| Đổi một field thường thành `transient` | **Có** | Default serialized fields thay đổi |
| Đổi một field instance thành `static` | **Có** | Static fields không thuộc default instance state |
| Thêm method `readObject` đúng chữ ký và có code sửa field | **Có** | Runtime gọi hook; code trong body thay đổi state |
| Đổi logic trong `readObject` nhưng giữ `@Serial` | **Có** | Logic thực thi mới khác |
| Xóa `@Serial` nhưng giữ nguyên method `readObject` hợp lệ | **Không**, xét riêng annotation | Hook vẫn có tên/signature đúng |
| Đổi `serialVersionUID` | **Có thể** thay đổi khả năng đọc stream cũ | Kiểm tra class descriptor compatibility |
| Đổi `serialPersistentFields` hợp lệ | **Có** | Danh sách serialized fields có thể khác |
| Thêm `writeReplace`/`readResolve` hợp lệ | **Có** | Có thể thay thế object viết/đọc |
| Chỉ đổi comment hoặc Javadoc `@serial` | Không tự đổi runtime serialization | Tài liệu/metadata mô tả, không phải hook |
| Thay đổi lớp `record` | Có thể đổi serialized form của record | Giao thức record có quy tắc riêng, không do `@Serial` |

**Câu hỏi review hữu ích:** “Nếu tôi xóa riêng annotation `@Serial` và giữ nguyên mọi thứ khác, serialization behavior có thay đổi không?” Với `java.io.Serial`, **không**. Nếu có khác biệt, cần điều tra chỗ code/build khác đã thay đổi, không vội gán nguyên nhân cho annotation.

## 8. Đừng nhầm `@Serial` với những thứ có tên gần giống

### 8.1. `@Serial` (annotation) và `@serial` (Javadoc tag)

Hai cú pháp khác nhau:

~~~java
/**
 * User-visible display name.
 * @serial Stored name exactly as provided.
 */
private String name;

@Serial
private static final long serialVersionUID = 1L;
~~~

Đoạn này nằm trong class serializable có import `java.io.Serial`.

- `@Serial` **chữ S hoa**, đứng trước một declaration, được Java compiler hiểu là annotation type `java.io.Serial`.
- `@serial` **chữ s thường**, nằm **trong Javadoc comment**, dùng để tài liệu hóa serialized form; công cụ `javadoc` có thể dùng khi tạo serialized-form documentation.
- Cả hai **không tự động biến đổi giá trị field**, nhưng phục vụ hai mục đích khác nhau: **kiểm tra khai báo** và **tài liệu hóa**.

### 8.2. `@Serial` và serialization của JSON framework

Một framework JSON có thể dùng annotation được giữ ở runtime hoặc thông tin cấu hình riêng để đổi tên property, bỏ trường, đổi định dạng thời gian, v.v. `java.io.Serial` **không phải** annotation của Jackson, Gson, JPA hay một cơ chế mã hóa JSON.

Ví dụ:

~~~text
Java Object Serialization:
    Serializable + ObjectOutputStream/ObjectInputStream
    + writeObject/readObject/serialPersistentFields/serialVersionUID
    + @Serial là dấu hiệu hỗ trợ compiler

JSON serialization:
    thư viện JSON và value model, cấu hình, mapping rules
    + @Serial không tự quyết định JSON property
~~~

Một class có `@Serial` không mặc nhiên được tự động chuyển thành JSON theo một quy tắc đặc biệt. Muốn có JSON contract, dùng serializer/schema và cấu hình đúng với thư viện mà dự án sử dụng.

### 8.3. `Serializable` (interface) và `@Serial` (annotation)

~~~java
final class Data implements java.io.Serializable {
    @java.io.Serial
    private static final long serialVersionUID = 1L;
}
~~~

- `Serializable` là **marker interface**, có ý nghĩa runtime đối với cơ chế Java serialization.
- `@Serial` là **source annotation** nhằm kiểm tra và diễn đạt vai trò của các field/method đặc biệt.
- Lớp chỉ có `@Serial` nhưng **không serializable** không trở thành serializable.
- Lớp đã implements `Serializable` vẫn có thể hoạt động **không có `@Serial`**; tuy nhiên dùng annotation đúng chỗ giúp code rõ ràng và phát hiện lỗi sớm hơn.

## 9. Các trường hợp đặc biệt còn hiện hành

### 9.1. `Externalizable`

`java.io.Externalizable` **extends `Serializable`** nhưng giao thức của nó dùng hai method `writeExternal(ObjectOutput)` và `readExternal(ObjectInput)` cùng các yêu cầu về constructor. Các method này **không phải** năm special methods để gắn `@Serial` theo bảng của Javadoc.

Theo `java.io.Serial` Javadoc, trong một lớp `Externalizable`, các khai báo `writeObject`, `readObject`, `readObjectNoData` và `serialPersistentFields` **không được giao thức tương ứng sử dụng**. Annotate những khai báo vô hiệu ấy là sai về ý nghĩa; đừng cho rằng `@Serial` khiến chúng hoạt động trở lại.

Nếu cần `Externalizable`, hiểu đầy đủ giao thức, quyền public constructor và rủi ro dữ liệu; nó **không** phải giải pháp đơn giản để tự động làm sạch dữ liệu.

### 9.2. `enum`

Java enum có cơ chế serialization đặc biệt. Theo Javadoc, `serialVersionUID` do enum khai báo **không điều khiển phiên bản như class serializable thông thường**; enum có UID cố định `0L`. Các special serialization methods `writeObject`/`readObject`/`readObjectNoData`/`writeReplace`/`readResolve` trong enum **không được sử dụng** như ở lớp thường.

Gắn `@Serial` lên một khai báo vốn không hiệu lực **không thể làm enum thay đổi giao thức serialization**. Khi cần hiểu giá trị khôi phục của enum, xem phần enum trong Java Serialization Specification, không áp quy tắc của class thông thường.

### 9.3. `record` implement `Serializable`

**Record** có giao thức serialization riêng đã ổn định trong Java hiện hành. Các record components xác định dữ liệu; trong deserialization, **canonical constructor** được gọi để tạo record. Các method `writeObject`, `readObject` và `readObjectNoData` định nghĩa trên record **bị bỏ qua**, cũng như `serialPersistentFields`; nhưng `writeReplace` và `readResolve` vẫn có thể tham gia theo quy tắc áp dụng.

Vì vậy, ngay cả một annotation `@Serial` đúng kiểu source annotation cũng **không tự làm các method bị record serialization bỏ qua trở thành hook hoạt động**. Nếu record cần kiểm tra dữ liệu hợp lệ, nên thiết kế bất biến trong constructor và hiểu kỹ giao thức record/serialization hiện hành.

### 9.4. Nested class và thay đổi version

Khi dùng Java serialization cho class nested/inner, chú ý các giới hạn trên inner classes không static, cấu trúc enclosing instance và compatibility. Không lấy việc thêm `@Serial` làm cách khắc phục các lỗi về class evolution, UID hoặc serialized state. Khi phải lưu dữ liệu lâu dài, có kế hoạch versioning và test đọc dữ liệu cũ.

## 10. Những lỗi suy luận phổ biến

| Hiểu sai | Điều đúng | Cách kiểm chứng |
| --- | --- | --- |
| “`@Serial` làm field tự được mã hóa.” | Annotation không mã hóa nội dung. | Đọc source và round-trip một object mẫu. |
| “Có `@Serial` thì class tự `Serializable`.” | Cần cơ chế serializability riêng. | Kiểm tra implements và thử `ObjectOutputStream`. |
| “Thêm `@Serial` vào `readObject` khiến runtime bắt đầu gọi method.” | Runtime gọi vì method hợp lệ, không vì annotation. | Dùng demo `MarkedHook`/`UnmarkedHook`. |
| “Bỏ `@Serial` thì hook ngừng chạy.” | Hook vẫn chạy nếu giữ đúng chữ ký. | So sánh output hai class trong ví dụ. |
| “`@Serial` tự loại mật khẩu khỏi stream.” | Default serial fields và code ghi dữ liệu mới quyết định. | Dùng `transient`/data minimization, review custom hook. |
| “`serialVersionUID` tự đổi dữ liệu theo version mới.” | UID chủ yếu kiểm tra tương thích. | Test đọc stream giữa phiên bản lớp. |
| “`@Serial` xuất hiện khi reflection tìm annotation ở runtime.” | Retention `SOURCE`, không được giữ trong classfile. | `isAnnotationPresent(Serial.class) == false`. |
| “Compiler nhất định báo lỗi nếu dùng `@Serial` sai.” | Javadoc khuyến khích kiểm tra/cảnh báo; policy tùy compiler/options. | Chạy `javac -Xlint:serial`, xem diagnostics. |
| “`@Serial` thay thế `@serial` trong Javadoc.” | Một cái là annotation, cái kia là documentation tag. | Xem mã Java và serialized-form docs. |
| “`@Serial` điều khiển JSON/JPA mapping.” | Không thuộc các framework đó. | Xem serializer/framework configuration. |
| “Có `@Serial` thì `ObjectInputStream` an toàn trước dữ liệu lạ.” | Deserialization untrusted input có rủi ro lớn. | Tránh input lạ; thiết kế filter/chính sách dữ liệu. |
| “Cứ thêm `@Serial` vào method của record/enum thì sẽ hoạt động.” | Record và enum có special serialization rules. | Đối chiếu spec và test đúng loại lớp. |
| “Mọi field static hoặc transient được ghi chỉ vì có annotation.” | Default protocol không ghi chúng như instance state. | Round-trip, kiểm tra bytes/state và custom hook. |

## 11. Nguyên tắc bảo mật khi dùng Java Object Serialization

**`@Serial` không phải công cụ security.** Java Object Serialization có thể dựng lại object graph, tải class và kích hoạt các callback tương ứng khi deserialization. **Đọc byte stream không đáng tin bằng `ObjectInputStream` tiềm ẩn rủi ro lớn** và không nên là lựa chọn mặc định cho thông điệp từ người dùng hoặc service lạ.

Các biện pháp cần cân nhắc:

1. **Tránh native deserialization đối với dữ liệu không tin cậy** khi có thể; dùng định dạng dữ liệu có schema rõ ràng và parser phù hợp.
2. Nếu một hệ thống bắt buộc dùng Java serialization, áp dụng **`ObjectInputFilter`** phù hợp để giới hạn class, chiều sâu graph, số references, kích thước array/stream; dùng stream-specific hoặc JVM-wide filter theo kiến trúc.
3. Đặt giới hạn resource và xác thực/ủy quyền cho nghiệp vụ; **filter không tự bảo đảm mọi logic an toàn**.
4. Không nhúng secrets vào stream; `transient` có thể giúp default serialization bỏ một field, nhưng custom hook vẫn phải được review.
5. Không tin rằng annotation `@Serial` làm dữ liệu được sanitize, validate, encrypt hoặc chống gadget attacks.
6. Có test đọc dữ liệu cũ và kiểm tra bất biến object sau deserialization khi serialization form là hợp đồng thực tế.

**Quan trọng:** ví dụ `roundTrip` ở mục 5 deserialize duy nhất **bytes do chính chương trình mới tạo trong memory**, nhằm học API. Không dùng đoạn mã đó làm endpoint đọc mọi byte từ mạng chỉ vì nó biên dịch và chạy đúng.

## 12. Checklist code review và CI

- [ ] Class thực sự là `Serializable` nếu dùng Java Object Serialization; `@Serial` không thay marker interface.
- [ ] `@Serial` chỉ nằm trên những field/method serialization-related đã được Java định nghĩa, đúng chữ ký và ngữ cảnh.
- [ ] `serialVersionUID` khi khai báo có kiểu `private static final long` và giá trị do nhóm chọn theo chính sách compatibility.
- [ ] `serialPersistentFields` nếu sử dụng có đúng kiểu và được kết hợp với logic mapping tương ứng.
- [ ] `writeObject`, `readObject`, `readObjectNoData` có chữ ký chính xác; `readResolve`/`writeReplace` đúng hợp đồng.
- [ ] Không nhầm annotation `SOURCE` với runtime serialization hook.
- [ ] Mọi hành vi chuyển đổi state đều có **câu lệnh và test rõ**, không chỉ có annotation.
- [ ] Các fields `transient`/`static` được xét theo đúng quy tắc default serialization.
- [ ] Có test cả trường hợp **hook có annotation và hook không annotation** nếu bài toán là chứng minh source annotation không tạo runtime behavior.
- [ ] Biên dịch với `-Xlint:serial` trên JDK/toolchain đã khóa, xem và xử lý warnings cần thiết.
- [ ] Không test cảnh báo bằng cách dựa vào chính xác wording từ một bản javac cụ thể.
- [ ] Không áp quy tắc của regular class cho enum, Externalizable hoặc record một cách máy móc.
- [ ] Với dữ liệu không đáng tin, hạn chế hoặc tránh Java native deserialization; dùng `ObjectInputFilter` và kiểm tra quyền/resource khi không tránh được.
- [ ] Ghi tài liệu serialized form nếu nó là hợp đồng cần tương thích, không chỉ dựa vào việc thêm `@Serial`.

## 13. Bài tập tự luyện

1. Chạy `SerialBehaviorDemo` trên JDK 17+, giải thích nguyên nhân thực sự của **từng** dòng stdout.
2. Bỏ `@Serial` ở method `MarkedHook.readObject` nhưng không sửa chữ ký/thân hàm. Dự đoán và kiểm chứng kết quả runtime.
3. Bỏ câu `text = text.strip();` nhưng giữ `@Serial`. Kết quả giá trị `text` thay đổi như thế nào? Vì sao?
4. Bỏ `transient` ở `Plain.token`. Khi round-trip, giá trị `token` có thể được phục hồi không? Annotation `@Serial` có liên quan không?
5. Dùng reflection kiểm tra `Plain.serialVersionUID` có `@Serial` tại runtime không. Vì sao `false` vẫn phù hợp với Javadoc?
6. Biên dịch `BadSerialDeclaration.java` với `-Xlint:serial`, phân biệt warning ở compile-time và hook nào sẽ thực sự được serialization runtime nhận diện.
7. Đổi giá trị `serialVersionUID` và thử đọc dữ liệu cũ đã lưu. Phân biệt **compatibility check** với **data migration**.
8. Viết một class `Serializable` có `writeObject`/`readObject` để ghi và đọc một giá trị theo format riêng. Sau đó bỏ `@Serial` và kiểm tra cùng logic còn hoạt động.
9. Mô tả sự khác nhau giữa `serialPersistentFields` hợp lệ và `@Serial` đặt trên field đó.
10. Nêu cách xử lý dữ liệu không đáng tin nếu ứng dụng bắt buộc đọc Java serialized stream. Vì sao chỉ có `@Serial` không giúp?
11. Vì sao `@serial` trong Javadoc không phải `@Serial` của Java code? Tìm ví dụ tài liệu hóa serialized form.
12. So sánh một class bình thường với một `record implements Serializable`: vì sao không nên dùng `@Serial` để “kích hoạt” `readObject` trên record?

## 14. Tài liệu chuẩn còn áp dụng

- [Oracle Java SE 25 – `java.io.Serial`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/Serial.html): phạm vi `METHOD/FIELD`, `Retention(SOURCE)`, hai field và năm method serialization-related, khuyến khích compiler warning cho khai báo không đúng.
- [Oracle Java SE 25 – `Serializable`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/Serializable.html): ý nghĩa marker interface và các special serialization methods.
- [Oracle Java SE 25 – `ObjectInputStream`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/ObjectInputStream.html): default deserialization, `readObject` và cảnh báo an toàn khi đọc dữ liệu không đáng tin.
- [Oracle Java SE 25 – `ObjectOutputStream`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/ObjectOutputStream.html): ghi state và giao thức tùy biến bằng `writeObject`.
- [Oracle Java SE 25 – Java Object Serialization Specification, System Architecture](https://docs.oracle.com/en/java/javase/25/docs/specs/serialization/serial-arch.html): serialPersistentFields, special methods, quy tắc enum và record.
- [Oracle Java SE 25 – `ObjectInputFilter`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/ObjectInputFilter.html): lọc các class và giới hạn resource khi deserialize.
- [Oracle Java SE 25 – `javac` manual](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): `-Xlint:serial` và các lựa chọn kiểm soát cảnh báo.

**Ghi nhớ:** **`@Serial` là một dấu hiệu ở source code nhằm giúp compiler nhận diện khai báo serialization-related.** Nó **không sửa dữ liệu runtime**. Nếu dữ liệu thay đổi sau serialize/deserialize, hãy tìm **`transient`, serialized fields, `serialVersionUID` compatibility, custom `writeObject`/`readObject`, `writeReplace`/`readResolve` hoặc logic application**. Đó mới là những thành phần quyết định behavior.