# Field final, static final và field của record: đối chiếu giới hạn ghi theo hợp đồng JDK hiện hành

## 1. Tại sao cần kiểm chứng giới hạn ghi bằng reflection?

Trong Java, từ khóa `final` ngăn mã Java thông thường gán lại một field sau khi field đã được khởi tạo hợp lệ. Khi dùng `java.lang.reflect.Field`, việc một field **có thể được đọc** hoặc **bỏ qua kiểm tra truy cập Java thông thường** không đồng nghĩa field đó **có thể bị ghi**.

Ví dụ, một thư viện serialization, dependency injection hoặc mapper có thể gọi:

~~~java
field.trySetAccessible();
field.set(object, newValue);
~~~

Đoạn mã trên có thể thành công với field thông thường, nhưng thất bại với `static final`, field `final` của `record` hoặc với field `final` thông thường trong một số cấu hình JDK hiện đại.

Bài này thuộc chương **Hợp đồng reflection** của module Java 18. Mục tiêu là đối chiếu hợp đồng `Field` vẫn áp dụng trên các JDK hiện đại, nhận diện khác biệt giữa *được phép truy cập* và *được phép thay đổi giá trị*, đồng thời chọn cách thiết kế tránh phụ thuộc vào hành vi can thiệp field `final`.

## 2. Ba nhóm field cần phân biệt

Xét các kiểu dữ liệu sau:

~~~java
final class Account {
    private int retryCount;
    private final String accountId;

    Account(String accountId) {
        this.accountId = accountId;
    }
}

final class Defaults {
    static final int MAX_RETRIES = 3;
}

record AccountSnapshot(String accountId, int retryCount) {}
~~~

| Field | Bản chất | Ghi bằng `Field.set(...)` |
| --- | --- | --- |
| `Account.retryCount` | Instance field không `final` | Có thể ghi nếu đáp ứng kiểm tra quyền truy cập, kiểu dữ liệu và receiver hợp lệ. |
| `Account.accountId` | Instance field `final` của lớp thông thường | Bị giới hạn. Một số trường hợp deep reflection từng cho phép ghi sau khi mở quyền truy cập; JDK mới có thể cảnh báo hoặc từ chối theo chính sách final-field mutation. Không coi việc ghi thành công là bảo đảm phổ quát. |
| `Defaults.MAX_RETRIES` | `static final` | **Không thể** cấp quyền ghi qua `setAccessible(true)` hoặc `trySetAccessible()`. |
| `AccountSnapshot.accountId` và `retryCount` | Instance field `private final` do record khai báo ngầm cho các component | **Không thể** cấp quyền ghi qua `setAccessible(true)` hoặc `trySetAccessible()`. |

Cả field `final` thông thường, `static final` và field component của `record` đều có thể báo `Modifier.isFinal(field.getModifiers()) == true`. Vì vậy, kiểm tra **chỉ** modifier `final` là chưa đủ để suy ra kết quả `Field.set`.

Một `record` vẫn có thể khai báo **static field** riêng theo quy tắc Java. Khi nói “field của record” trong bài này, trọng tâm là các **instance field `private final` tương ứng với record component**. Quy tắc “không cấp quyền ghi” áp dụng cho mọi field `final` được khai báo trong record class; nó không tự động cấm ghi vào một `static` field **không final** do record khai báo.

## 3. Các bước quyết định trước khi Field.set có thể ghi

Có thể hình dung việc ghi qua reflection theo các lớp điều kiện:

~~~mermaid
flowchart TD
    A["Field.set(receiver, value)"] --> B{"Field có truy cập được?"}
    B -->|Không| X["Từ chối: IllegalAccessException hoặc lỗi mở truy cập"]
    B -->|Có| C{"Field thuộc nhóm không thể cấp quyền ghi?"}
    C -->|"static final; final trong record; final trong hidden class"| D["Không được ghi: IllegalAccessException"]
    C -->|Không| E{"Là instance final của lớp thường?"}
    E -->|Có| F["Phụ thuộc điều kiện deep reflection và chính sách JDK; không được bảo đảm"]
    E -->|Không| G["Kiểm tra receiver, kiểu giá trị và chuyển đổi hợp lệ"]
    F --> G
    G -->|Hợp lệ và cho phép| H["Thực hiện ghi"]
    G -->|Không hợp lệ| I["Báo ngoại lệ phù hợp"]
~~~

**Phần quyền truy cập** phụ thuộc vào tính nhìn thấy của lớp và field, module chứa chúng, quan hệ package/module, và việc có được phép bỏ qua kiểm tra truy cập hay không. **Phần khả năng ghi** là quy tắc riêng: mở truy cập không làm `static final` hoặc field `final` của record trở thành field có thể ghi.

### Vai trò của các API reflection

- `getDeclaredField("name")` lấy field được khai báo tại một lớp, kể cả field `private`; thao tác lấy đối tượng `Field` **không cấp quyền đọc/ghi**.
- `canAccess(receiver)` trả lời đối tượng `Field` hiện có thể truy cập trên receiver tương ứng hay không, theo tình trạng access checks. Nó **không kiểm tra độc lập** field có được phép ghi hay không.
- `trySetAccessible()` thử mở quyền truy cập và trả về `true` hoặc `false` nếu bị giới hạn bởi quy tắc truy cập/module. Kết quả `true` **không hứa hẹn** `Field.set` sẽ thành công.
- `setAccessible(true)` thử mở quyền truy cập; có thể ném `InaccessibleObjectException` khi không được phép mở qua ranh giới module.
- `Field.get(receiver)` và `Field.set(receiver, value)` là hai thao tác độc lập; đọc thành công không chứng minh ghi thành công.

Với `static` field, receiver có thể là `null`. Với instance field, receiver phải là đối tượng phù hợp; truyền sai receiver hoặc giá trị sai kiểu sẽ tạo lỗi khác với lỗi truy cập, ví dụ `IllegalArgumentException`.

## 4. Tại sao setAccessible(true) không “phá được” mọi final?

Javadoc của `AccessibleObject.setAccessible` và `Field.set` phân biệt rõ giữa **suppress access checks** và **write access**. Đối với những field được quy định là *non-modifiable final fields*, deep reflection chỉ có thể mở **quyền đọc**; không thể mở quyền ghi.

Nhóm quan trọng gồm:

1. **`static final` field** được khai báo trong class hoặc interface.
2. **`final` field được khai báo trong record class**, bao gồm field của record component.
3. **`final` field được khai báo trong hidden class**.

Hidden class là trường hợp bổ sung của hợp đồng hiện đại; bài này không dựa vào thủ thuật tạo hidden class vì trọng tâm là class và record thông thường.

Hai biểu thức sau không tương đương:

~~~java
boolean readable = field.trySetAccessible(); // Mở kiểm tra truy cập khi được phép.
field.set(receiver, value);                  // Thao tác ghi có hợp đồng riêng.
~~~

Chẳng hạn, trong cùng module, `trySetAccessible()` trên `static final` có thể trả về `true` để hỗ trợ `get(null)`. Sau đó `set(null, 100)` vẫn phải thất bại vì không có khả năng ghi. Đây **không phải lỗi của trySetAccessible**.

## 5. Chương trình tự chạy để so sánh bốn tình huống

Đoạn dưới đây là một chương trình Java tự chứa. Nó có thể dùng trên JDK hỗ trợ record và các API reflection tương ứng. Mục đích là **quan sát hợp đồng**, không nhằm cung cấp thủ thuật sửa field `final` trong ứng dụng.

Tệp `ReflectionFieldContractDemo.java`:

~~~java
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;

public class ReflectionFieldContractDemo {

    static final class MutableBox {
        private int count = 1;
    }

    static final class OrdinaryFinalBox {
        private final int count;

        OrdinaryFinalBox(int count) {
            this.count = count;
        }

        int count() {
            return count;
        }
    }

    static final class Constants {
        private static final int LIMIT = 5;
    }

    record Snapshot(int count) {}

    static void inspectAndTryWrite(
            String label, Field field, Object receiver, Object newValue)
            throws Exception {

        System.out.println("\n--- " + label + " ---");
        System.out.println("modifiers = "
                + Modifier.toString(field.getModifiers()));
        System.out.println("declaring class is record = "
                + field.getDeclaringClass().isRecord());

        boolean accessible = field.trySetAccessible();
        System.out.println("trySetAccessible = " + accessible);

        if (!accessible) {
            System.out.println("Không thể mở quyền truy cập; bỏ qua ghi.");
            return;
        }

        System.out.println("reflection read before = " + field.get(receiver));

        try {
            field.set(receiver, newValue);
            System.out.println("Field.set: SUCCESS");
            System.out.println("reflection read after  = " + field.get(receiver));
        } catch (IllegalAccessException ex) {
            System.out.println("Field.set: IllegalAccessException");
        } catch (IllegalArgumentException ex) {
            System.out.println("Field.set: IllegalArgumentException: "
                    + ex.getMessage());
        }
    }

    public static void main(String[] args) throws Exception {
        MutableBox mutable = new MutableBox();
        inspectAndTryWrite(
                "mutable instance",
                MutableBox.class.getDeclaredField("count"),
                mutable, 2);

        OrdinaryFinalBox ordinaryFinal = new OrdinaryFinalBox(10);
        inspectAndTryWrite(
                "ordinary final instance",
                OrdinaryFinalBox.class.getDeclaredField("count"),
                ordinaryFinal, 20);

        inspectAndTryWrite(
                "static final",
                Constants.class.getDeclaredField("LIMIT"),
                null, 6);

        Snapshot record = new Snapshot(30);
        inspectAndTryWrite(
                "record component field",
                Snapshot.class.getDeclaredField("count"),
                record, 40);
    }
}
~~~

Biên dịch và chạy trên một JDK đang được sử dụng:

~~~bash
javac ReflectionFieldContractDemo.java
java ReflectionFieldContractDemo
~~~

### Cách đọc kết quả

| Tình huống | Điều nên quan sát |
| --- | --- |
| `mutable instance` | Trong ví dụ cùng lớp bao ngoài, quyền truy cập có thể mở; `Field.set` ghi thành công và `Field.get` phản ánh giá trị mới. |
| `ordinary final instance` | **Không ấn định một kết quả cố định cho mọi JDK.** Kết quả phụ thuộc khả năng truy cập, loại field và chính sách final-field mutation của bản JDK/cách chạy. Có thể gặp cảnh báo hoặc `IllegalAccessException`; nếu ghi thành công, không suy ra hành vi đó là hợp đồng ổn định. |
| `static final` | Dù có thể đọc giá trị `LIMIT` bằng reflection, cố ghi phải gặp `IllegalAccessException`. |
| `record component field` | Dù có thể đọc `count` của `Snapshot` bằng reflection, cố ghi phải gặp `IllegalAccessException`. |

Đặc biệt, nếu reflection báo ghi `ordinary final instance` thành công, **không dùng kết quả ấy làm cam kết** rằng mã đã được biên dịch, mã được JIT tối ưu hoặc các thread khác đều quan sát giá trị mới một cách nhất quán. Các giả định về field `final` có ý nghĩa đối với Java Memory Model và tối ưu hóa. Việc sửa sau khi đối tượng đã được tạo hoàn chỉnh có thể dẫn tới hành vi khó dự đoán.

Ví dụ không dùng thư viện ngoài, không truy cập nội bộ JDK và không phụ thuộc quyền mở package của module khác. Khi chuyển sang kiểm thử thư viện nằm trong module riêng, cần xem thêm quy tắc JPMS bên dưới.

## 6. JDK mới và giới hạn của việc sửa final thông thường

Trước đây, một số framework dùng deep reflection để điền dữ liệu trực tiếp vào `private final` instance field của class thông thường sau khi tạo object. Đây là một cơ chế có ràng buộc hẹp và tiềm ẩn vấn đề về tính bất biến, khởi tạo object và tối ưu hóa.

Trên các JDK hiện đại, chính sách **final-field mutation** tiếp tục được siết theo hướng tôn trọng `final`. Vì vậy cần hiểu rõ:

- **Không có bảo đảm chung** rằng gọi `setAccessible(true)` rồi `Field.set` trên instance field `final` sẽ luôn hoạt động.
- Các bản JDK khác nhau hoặc cách khởi động khác nhau có thể cảnh báo, áp dụng quy tắc cấp quyền hoặc từ chối các thao tác deep reflection thay đổi `final`. Phải đối chiếu tài liệu và cấu hình của **đúng JDK đang chạy**.
- Các cơ chế cho phép tương thích, nếu JDK cung cấp, không biến `static final` hoặc field `final` của record thành field có thể ghi bằng `Field.set`.
- Ngay khi ghi được, sửa field `final` sau khởi tạo vẫn không phải kỹ thuật cập nhật trạng thái phù hợp cho business object.

Đừng khắc phục lỗi bằng cách vô hiệu hóa cơ chế kiểm soát `final` trên toàn ứng dụng. Với bài toán cần khôi phục dữ liệu, hãy ưu tiên constructor, factory method hoặc cơ chế serialization/deserialization chính thức của thư viện.

### Không nhầm reflection với cơ chế truy cập khác

`VarHandle`, `MethodHandle` và `MethodHandles.Lookup` cung cấp các cách truy cập member theo hợp đồng riêng. Chúng không phải “đường vòng” được khuyến nghị để sửa `static final` hoặc field `final` của record. Ví dụ, chế độ ghi của `VarHandle` trên một final field không trở thành khả dụng chỉ vì có thể đọc field đó.

Không sử dụng các API nội bộ, kỹ thuật bytecode không được hỗ trợ hoặc thủ thuật thay giá trị hằng số để vượt qua quy tắc của `Field`. Đặc biệt, giá trị `static final` là hằng số compile-time có thể đã được biên dịch vào nơi sử dụng; ngay cả việc thay đổi bộ nhớ qua cơ chế ngoài hợp đồng cũng không chứng minh mọi caller nhận giá trị mới.

## 7. JPMS: mở package giải quyết vấn đề truy cập, không thay đổi tính final

Trên Java 18 và những JDK hiện đại, tính đóng gói module là một phần quan trọng của reflection.

Giả sử field nằm trong module có tên `com.example.model` và framework phản chiếu nằm trong module `com.example.mapper`. Để cho phép deep reflection vào package của model, module cung cấp có thể chủ động khai báo:

~~~java
module com.example.model {
    exports com.example.model.api;
    opens com.example.model.internal to com.example.mapper;
}
~~~

`exports` chủ yếu cấp quyền truy cập Java thông thường tới các kiểu public của package được export. `opens` cho phép reflection sâu vào member không public của package đích cho module được nêu, theo quy tắc JPMS.

Điều này dẫn đến ba kết quả khác nhau:

1. Một `private int` trong package được mở có thể được ghi qua reflection nếu receiver và kiểu dữ liệu hợp lệ.
2. Một `private final int` trong class thông thường vẫn chịu các giới hạn final-field mutation của JDK.
3. Một `private static final int` hoặc `private final int` là record component vẫn thuộc nhóm **không thể cấp quyền ghi**, dù package đã `opens`.

Cấu hình mở module từ command line như `--add-opens` cũng chỉ là công cụ thay đổi phạm vi truy cập, không phải lệnh làm mất ràng buộc `final`.

**Thực hành tốt:** Framework nên yêu cầu quyền tối thiểu cần thiết; thư viện dữ liệu nên cung cấp constructor hoặc API công khai để nhận giá trị thay vì yêu cầu quyền ghi sâu vào field `final`.

## 8. Record: đọc cấu trúc, tạo bản mới thay cho sửa field

Record được dùng để mô tả một dạng dữ liệu có cấu trúc, với các component và các thành phần do compiler tạo theo hợp đồng Java. Ví dụ:

~~~java
public record OrderView(String orderId, int quantity) {

    public OrderView {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }
        if (quantity < 0) {
            throw new IllegalArgumentException("quantity must be non-negative");
        }
    }

    public OrderView withQuantity(int nextQuantity) {
        return new OrderView(orderId, nextQuantity);
    }
}
~~~

Để cập nhật số lượng, thay vì phản chiếu vào field `quantity`:

~~~java
OrderView original = new OrderView("A-01", 2);
OrderView updated = original.withQuantity(3);

System.out.println(original.quantity()); // 2
System.out.println(updated.quantity());  // 3
~~~

Constructor của record là nơi kiểm tra bất biến. Tạo bản mới bằng constructor cũng giữ nguyên các điều kiện kiểm tra được khai báo.

Khi muốn biết record có những component nào, ưu tiên API record thay vì tự suy luận bằng tên field:

~~~java
import java.lang.reflect.RecordComponent;
import java.util.Arrays;

RecordComponent[] components = OrderView.class.getRecordComponents();

Arrays.stream(components).forEach(component ->
        System.out.println(component.getName()
                + " : " + component.getType().getTypeName()));
~~~

`getRecordComponents()` thể hiện cấu trúc record ở mức API. Việc lấy `Field` ẩn bên dưới qua `getDeclaredField("quantity")` có thể phục vụ việc đọc/chẩn đoán nhưng không cấp quyền ghi.

**Record bất biến nông (shallow immutability):** Component field không thể bị gán lại, nhưng object mà component trỏ tới có thể vẫn mutable. Ví dụ record chứa `List` có thể tham chiếu đến một list có thể sửa nội dung. Nếu cần snapshot bất biến, tạo defensive copy như `List.copyOf(...)` tại constructor. Ràng buộc của `Field.set` chỉ bảo vệ việc thay *tham chiếu trong field*, không tự động đóng băng toàn bộ object graph.

## 9. Thiết kế mapper và deserializer không phụ thuộc vào đột biến final

Giả sử một dữ liệu đầu vào có hai thuộc tính `id` và `count`. Thay vì:

~~~java
// Mẫu nên tránh đối với final / record component:
// Field idField = type.getDeclaredField("id");
// idField.setAccessible(true);
// idField.set(instance, inputId);
~~~

hãy tạo đối tượng qua API khởi tạo có hợp đồng rõ ràng:

~~~java
record ItemDto(String id, int count) {}

static ItemDto toDto(String id, int count) {
    return new ItemDto(id, count);
}
~~~

Nếu sử dụng một framework serializer/deserializer, cần chọn cách cấu hình để nó gọi constructor/factory hoặc hỗ trợ record theo API công khai của framework đang dùng. Khi khởi tạo object hoàn chỉnh qua constructor, các quy tắc kiểm tra bất biến, tính hiển thị của `final` và tối ưu hóa Java thông thường có thể được áp dụng theo đúng hợp đồng.

Trong hệ thống dependency injection, ưu tiên constructor injection cho các dependency bắt buộc. Trong hệ thống cấu hình, ưu tiên tạo immutable configuration object mới khi cấu hình thay đổi; với trạng thái thường xuyên cập nhật, sử dụng field mutable được thiết kế có chủ đích, đồng thời xử lý đồng bộ/thread safety theo nhu cầu.

## 10. Kiểm chứng có hệ thống khi đổi JDK

Một phép kiểm chứng đúng phải phân biệt **không tìm được field**, **không mở được truy cập**, **không ghi được do final**, và **không ghi được do receiver/kiểu sai**. Không nên gom mọi lỗi thành “reflection không hỗ trợ”.

| Câu hỏi kiểm tra | API / tín hiệu | Cách diễn giải |
| --- | --- | --- |
| Có tìm đúng field được khai báo không? | `getDeclaredField` | `NoSuchFieldException` nghĩa là không có field tên đó ở declaring class được hỏi. |
| Field có `static` / `final` không? | `Modifier.isStatic / isFinal` | Phân loại trước khi ghi; chưa đủ để suy ra mọi quyền. |
| Declaring class có phải record không? | `getDeclaringClass().isRecord()` | Với record component, field là `private final`, không được ghi qua deep reflection. |
| Đã mở được kiểm tra truy cập chưa? | `trySetAccessible` hoặc `setAccessible` | Có thể thất bại theo luật module; mở được cũng chưa đủ điều kiện ghi. |
| `Field.set` có báo `IllegalAccessException` không? | `try/catch` | Có thể do quyền truy cập hoặc do tính không thể ghi của final field. |
| Có `IllegalArgumentException` không? | `Field.set` | Xem lại receiver, kiểu dữ liệu và phép chuyển đổi hợp lệ. |
| Thay đổi JDK có làm đổi kết quả instance final không? | Chạy lại trên đúng JDK/cấu hình | Ghi lại version, module configuration, cảnh báo và loại lỗi. |
| Có dựa vào giá trị vừa ghi sau khởi tạo không? | Kiểm tra thiết kế | Nên chuyển sang constructor/factory hoặc mutable state có chủ đích. |

Khi cần kiểm thử tự động, dùng một test khẳng định **ghi thành công** cho mutable field và hai test khẳng định **ghi bị từ chối** cho `static final` và record component, với điều kiện các field nằm trong phạm vi reflection có thể đọc. Tránh viết test buộc instance `final` thông thường phải ghi thành công trên mọi JDK.

Một bộ kiểm thử hợp lý gồm:

- **Positive:** `private int count`, package/module được phép mở, ghi đúng kiểu và xác minh giá trị đọc lại.
- **Negative bất biến:** `private static final int LIMIT`; sau khi có quyền đọc, gọi `Field.set(null, ...)` phải gặp `IllegalAccessException`.
- **Negative record:** `record State(int count)`; sau khi có quyền đọc, gọi `Field.set(state, ...)` phải gặp `IllegalAccessException`.
- **Compatibility observation:** `private final int count` của class thông thường; log phiên bản JDK, kết quả/cảnh báo nếu có, nhưng không coi việc ghi thành công là một quyền phổ quát.

Thử thêm một trường hợp module không mở package để phân biệt lỗi do JPMS với lỗi do `final`. Mọi thử nghiệm nên dùng đối tượng tạo mới và chỉ chạy trong môi trường test; không sửa các trường bất biến của đối tượng đang được chia sẻ trong ứng dụng.

## 11. Sai lầm thường gặp

### Sai lầm 1: “trySetAccessible trả true nên chắc chắn Field.set được”

Sai. `trySetAccessible` kiểm tra khả năng bỏ qua access checks. Nó không biến `static final` hoặc field `final` của record thành field có thể ghi.

### Sai lầm 2: “Mọi field có Modifier.FINAL đều có cùng hành vi”

Sai. `final` trên instance field lớp thường khác với `static final` và `final` field trong record. Ngoài ra các JDK hiện đại có thể áp dụng chính sách nghiêm hơn đối với việc sửa `final`.

### Sai lầm 3: “Mở module là đủ để sửa record”

Sai. `opens` chỉ cho phép truy cập sâu khi hợp lệ; field component của record vẫn không được cấp quyền ghi bằng `Field.set`.

### Sai lầm 4: “Đọc lại thấy giá trị mới tức là chương trình đã cập nhật an toàn”

Sai. Việc sửa `final` sau khởi tạo có thể xung đột với các giả định của compiler/JIT và mô hình bộ nhớ. Tránh xây dựng logic nghiệp vụ dựa vào kết quả này.

### Sai lầm 5: “Record là đối tượng bất biến sâu”

Sai. Các tham chiếu component không thể gán lại nhưng nội dung của object mutable được trỏ tới vẫn có thể thay đổi. Dùng defensive copy khi cần.

## 12. Câu hỏi tự kiểm tra

1. Tại sao `getDeclaredField("count")` trả về thành công nhưng `Field.set(...)` có thể ném `IllegalAccessException`?
2. Điều gì khác nhau giữa `trySetAccessible() == true` và khả năng ghi `static final`?
3. Tại sao một `private final` instance field của class thường cần được xem xét khác với `private final` component field của record?
4. `opens com.example.model.internal to com.example.mapper` thay đổi quyền gì? Vì sao nó không thay đổi giới hạn ghi của `final` trong record?
5. Tại sao nên tạo `new OrderView(...)` thay vì phản chiếu cập nhật field `quantity`?
6. Khi test ghi `private final` instance field cho kết quả khác sau khi nâng JDK, cần đối chiếu những yếu tố nào?
7. Record chứa `List<String>` có bất biến sâu không? Cần làm gì để tạo snapshot an toàn?
8. Vì sao không dùng `VarHandle` hay API nội bộ như một cách “sửa” các trường đã bị giới hạn theo hợp đồng reflection?

## 13. Ghi nhớ

- **Quyền truy cập và quyền ghi là hai hợp đồng khác nhau.** `setAccessible`/`trySetAccessible` không bảo đảm `Field.set` thành công.
- **`static final` và `final` field của record không thể được cấp quyền ghi bằng deep reflection.** Việc đọc được chúng không làm thay đổi quy tắc này.
- **`final` instance field của class thông thường chịu điều kiện và chính sách JDK.** Không thiết kế chức năng phụ thuộc việc sửa nó sau khởi tạo.
- **JPMS `opens` mở phạm vi reflection, không gỡ bỏ tính final.**
- **Ưu tiên constructor, factory, record constructor và trạng thái mutable có chủ đích** để mã còn đúng trên các JDK hiện hành và sau khi nâng cấp.

