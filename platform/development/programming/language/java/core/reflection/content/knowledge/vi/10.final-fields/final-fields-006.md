# Không xem sửa field là thay thế constructor và bất biến đối tượng

## 1. Bản chất vấn đề

Trong Java Reflection, `Field` cho phép quan sát metadata của trường và, trong những trường hợp được phép, thay đổi giá trị bằng `Field.set(Object, Object)`. Tuy nhiên, **ghi một field sau khi object đã được tạo ra không tương đương với việc khởi tạo object qua constructor**. Constructor là nơi tập trung quy tắc hợp lệ của dữ liệu, chuẩn hóa, tạo defensive copy, và thiết lập trạng thái nhất quán trước khi object được công bố để sử dụng.

Hãy tưởng tượng một đơn hàng có `amountCents >= 0`, mã đơn không rỗng và danh sách sản phẩm cố định. Nếu ai đó dùng Reflection viết trực tiếp `amountCents = -100` lên một object đã xây dựng, họ có thể làm sai invariant dù field đó khai báo `private final`. Nếu thay đổi danh sách bên trong mà không qua quy trình kiểm tra, các quy tắc liên quan cũng có thể không còn đúng.

Bài này trả lời các câu hỏi thực tế:

- Constructor tạo ra các bảo đảm gì mà `Field.set(...)` không tự tạo ra?
- `final` có nghĩa là bất biến hoàn toàn không? Có thể sửa final field bằng Reflection trong trường hợp nào?
- Vì sao “gọi Reflection thành công” không chứng minh object được khởi tạo hợp lệ hoặc an toàn giữa nhiều luồng?
- Nên thay đổi dữ liệu bằng cách nào để vẫn bảo toàn invariant?

**Nguyên tắc làm việc:** tạo object hợp lệ qua constructor/factory/builder, sau đó dùng API có kiểm soát để thay đổi trạng thái được phép; với object bất biến, tạo **instance mới** thay vì can thiệp vào field cũ.

## 2. Ba khái niệm cần phân biệt

### 2.1. Constructor thiết lập invariant

**Invariant** là điều kiện mà mọi object ở trạng thái sử dụng hợp lệ phải thỏa mãn. Ví dụ đối với `Receipt`:

- `orderId` không được `null` hoặc rỗng.
- `totalCents` không âm.
- `items` phải có ít nhất một sản phẩm.
- Danh sách sản phẩm không được thay đổi ngoài ý muốn sau khi object được tạo ra.

Constructor có thể kiểm tra tất cả điều kiện này **trước khi trả object cho caller**. Sau đó method hoặc factory của lớp có thể duy trì quy tắc tương tự khi cần thay đổi dữ liệu.

### 2.2. `final` bảo vệ phép gán vào biến/field, không tự bảo vệ toàn bộ đồ thị object

Với `private final int totalCents`, Java bình thường yêu cầu field được gán trong quá trình khởi tạo hợp lệ và không cho method Java thông thường gán lại nó về sau.

Với `private final List<String> items`, `final` **chỉ cố định tham chiếu** đến đối tượng `List`; nó không tự khóa nội dung của danh sách. Nếu nhận một `ArrayList` từ caller rồi giữ nguyên tham chiếu, caller vẫn có thể thêm/xóa phần tử, dù field chứa nó là `final`.

Bất biến cấp đối tượng cần thêm: không lộ tham chiếu mutable, defensive copy đầu vào/đầu ra, kiểm tra tất cả dữ liệu đầu vào, và không để phương thức cập nhật phá invariant.

### 2.3. `Field.set` là thao tác mức thấp lên trạng thái

`Field.set(receiver, value)` xét metadata field, receiver, quyền truy cập và khả năng gán giá trị/kiểu dữ liệu. Nó **không tự gọi lại constructor** của receiver, không tự áp dụng quy tắc nghiệp vụ, không kích hoạt validator tùy chỉnh, và không thực hiện defensive copy theo ý định thiết kế của class.

Ngay cả khi một lần ghi được Java Reflection chấp nhận, giá trị mới vẫn có thể làm object không hợp lệ theo domain. Vì vậy khả năng *thao tác kỹ thuật* không đồng nghĩa *quyền thay đổi hợp lệ theo mô hình đối tượng*.

## 3. Chương trình Java 17+: bảo toàn invariant bằng constructor và tạo instance mới

Lưu đoạn sau vào file **`FinalFieldGuidanceDemo.java`**. Đây là chương trình độc lập chỉ sử dụng thư viện chuẩn Java:

```java
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.List;

public class FinalFieldGuidanceDemo {
    static final class Receipt {
        private final String orderId;
        private final List<String> items;
        private final int totalCents;

        Receipt(String orderId, List<String> items, int totalCents) {
            if (orderId == null || orderId.isBlank()) {
                throw new IllegalArgumentException("orderId must not be blank");
            }
            if (items == null || items.isEmpty()) {
                throw new IllegalArgumentException("items must not be empty");
            }
            if (totalCents < 0) {
                throw new IllegalArgumentException("totalCents must be >= 0");
            }
            this.orderId = orderId;
            this.items = List.copyOf(items);
            this.totalCents = totalCents;
        }

        Receipt withTotal(int nextTotalCents) {
            return new Receipt(orderId, items, nextTotalCents);
        }

        String summary() {
            return orderId + " | " + items + " | " + totalCents;
        }
    }

    public static void main(String[] args) throws NoSuchFieldException {
        List<String> supplied = new ArrayList<>(List.of("Book"));
        Receipt original = new Receipt("ORD-1", supplied, 1200);

        supplied.add("Pen"); // Không làm thay đổi danh sách trong Receipt.
        System.out.println("Original: " + original.summary());

        Receipt updated = original.withTotal(1500);
        System.out.println("Updated: " + updated.summary());
        System.out.println("Original remains: " + original.summary());

        Field totalField = Receipt.class.getDeclaredField("totalCents");
        System.out.println("Declared final: "
                + Modifier.isFinal(totalField.getModifiers()));

        try {
            new Receipt("ORD-2", List.of("Pen"), -50);
        } catch (IllegalArgumentException e) {
            System.out.println("Invalid total: rejected");
        }

        try {
            original.items.add("Tape");
        } catch (UnsupportedOperationException e) {
            System.out.println("Mutating items: rejected");
        }
    }
}
```

Chạy tại thư mục chứa file:

```bash
javac --release 17 FinalFieldGuidanceDemo.java
java FinalFieldGuidanceDemo
```

Kết quả chuẩn:

```text
Original: ORD-1 | [Book] | 1200
Updated: ORD-1 | [Book] | 1500
Original remains: ORD-1 | [Book] | 1200
Declared final: true
Invalid total: rejected
Mutating items: rejected
```

**Ý nghĩa của ví dụ:**

1. Constructor kiểm tra mã đơn, danh sách và tổng tiền. Giá trị âm được từ chối ngay lúc tạo, nên không tồn tại instance hợp lệ có `totalCents < 0` do đường khởi tạo thông thường tạo ra.
2. `List.copyOf(items)` tạo dữ liệu lưu trữ không thể sửa qua các phép thêm/xóa, bảo vệ trước thay đổi từ danh sách caller cung cấp. Với phần tử kiểu `String` vốn bất biến, đây là cách phòng vệ đủ cho ví dụ. Với phần tử là object có trạng thái mutable, cần thêm chính sách sao chép sâu/thiết kế bất biến thích hợp.
3. `withTotal(...)` dựng một `Receipt` **mới** thông qua constructor, nên mọi invariant vẫn được kiểm tra. `original` không thay đổi; `updated` có giá trị mới.
4. `getDeclaredField("totalCents")` và `Modifier.isFinal(...)` đọc **metadata**, không can thiệp vào dữ liệu. Field là `private final` mà chương trình vẫn tìm được metadata.
5. Việc gọi `original.items.add(...)` bị chặn bởi danh sách bất biến. Trong chương trình, class bao ngoài được phép truy cập private member của nested class theo quy tắc nestmate; caller bên ngoài không nên trực tiếp đụng vào field private này.

**Thiết kế cần nhớ:** nếu có nghiệp vụ sửa tổng tiền, quyết định API là `withTotal(...)` hoặc một phương thức cập nhật có validation, chứ không phải thao tác `Field.set(...)` trực tiếp từ code sử dụng.

## 4. Cơ chế của `final` và Reflection trên Java 17–21

### 4.1. Khi nào `Field.set(...)` có thể thay đổi một final field?

Theo hợp đồng `java.lang.reflect.Field.set` ở Java 17/21, ghi field `final` bằng Reflection chỉ được phép trong điều kiện hẹp: việc tắt kiểm tra truy cập cho `Field` bằng `setAccessible(true)` đã **thành công**, field **không static**, và lớp khai báo **không phải hidden class hoặc record class**. Nếu không đáp ứng, `set` ném `IllegalAccessException`. Hơn nữa, `setAccessible(true)` tự nó có thể không được cho phép do ranh giới package/module.

| Kiểu field | Ý nghĩa thực tế |
| --- | --- |
| `private final int n` trong instance class thông thường | Có thể được phép ghi bởi Reflection **nếu** suppression hợp lệ và các điều kiện API khác thỏa mãn; không phải cách sửa domain object |
| `static final int N` | Không thể dùng `Field.set` để ghi như một instance final field; kể cả suppression không cấp write access cho static final |
| Thành phần record (`record Receipt(...)`) | Field final của record thuộc nhóm không cho viết qua `Field.set` |
| Final field khai báo trong hidden class | Cũng thuộc nhóm không cho viết qua `Field.set` |
| Instance field không final | Có thể ghi nếu receiver, kiểu giá trị và quyền truy cập phù hợp; vẫn có thể phá invariant nếu bypass API |

Không được kết luận “`private final` thì Reflection luôn không sửa được”, cũng không được kết luận “`setAccessible(true)` sẽ luôn sửa được mọi thứ”. Cả hai phát biểu đều sai về phạm vi.

### 4.2. Ví dụ **phản mẫu**: bypass validation

Đoạn sau chỉ minh họa vấn đề; **không phải đoạn cần chạy để cập nhật object trong ứng dụng**. Giả sử đang trong `main` của chương trình ở mục 3 và có biến `original`:

```java
Field f = Receipt.class.getDeclaredField("totalCents");

// Chỉ khi được phép bởi access/module rules; có thể bị từ chối.
if (f.trySetAccessible()) {
    // Phản mẫu: bỏ qua validation trong Receipt constructor.
    f.set(original, -100);
}
```

Nếu lệnh ghi thực sự thành công trong môi trường hỗ trợ trường hợp này, dữ liệu có thể vi phạm `totalCents >= 0`. Đặc biệt, **không dựa vào các getter/instructions tiếp theo để chứng minh mọi nơi đã thấy giá trị mới**, vì cơ chế tối ưu hóa đối với `final` khiến việc sửa sau khởi tạo có những hệ quả khó dự đoán.

Đừng nhầm `trySetAccessible()` trả `true` với việc field đã được ghi thành công: nó chỉ cho biết nỗ lực bật suppression thành công, còn `Field.set(...)` có thể thất bại ở điều kiện final, receiver hoặc kiểu dữ liệu.

### 4.3. `setAccessible` và JPMS không phải cơ chế chuyển một API kín thành public

Với named module (JPMS), quyền deep reflection còn phụ thuộc package có được `opens` cho module đang gọi hay không. `exports` hỗ trợ tiếp cận public API trong các điều kiện thông thường, nhưng không tự cho phép chỉnh sửa private final field. Nhiều thư viện framework phải cấu hình `opens` rõ ràng nếu thực sự cần deep reflection.

Ngay cả khi có quyền deep reflection, **việc sửa field bỏ qua constructor vẫn không được tự động xem là hợp lệ** về nghiệp vụ và an toàn đồng thời.

## 5. Vì sao constructor có ý nghĩa đặc biệt trong Java Memory Model?

Java Language Specification (JLS `17.5) quy định **final field semantics** cho các field final được khởi tạo đúng cách. Khi constructor hoàn tất, một **freeze action** gắn với final field giúp hỗ trợ việc quan sát các giá trị đã khởi tạo đúng trong điều kiện mô hình bộ nhớ quy định. Quy tắc sử dụng cơ bản:

1. Gán các final field trong quá trình khởi tạo hợp lệ.
2. Không làm rò rỉ tham chiếu `this` tới luồng/đối tượng khác **trước khi constructor kết thúc**.
3. Sau khi khởi tạo, không xem final field là nơi lưu trạng thái cần liên tục thay đổi.

Đây là một lý do `final` hỗ trợ thiết kế immutable class an toàn giữa các luồng. Tuy nhiên, **final-field guarantees không phải phép màu bảo đảm mọi object đa luồng đều thread-safe**. Nếu final field trỏ đến một object mutable, các thay đổi sau đó trên object được trỏ tới vẫn phải tuân thủ quy tắc đồng bộ riêng.

### 5.1. Phép ghi phản chiếu sau constructor có semantics đặc biệt và hạn chế

JLS `17.5.3 thừa nhận vài trường hợp đặc biệt như deserialization/reconstruction phải điều chỉnh final field sau khi tạo object. Mô hình có ý nghĩa trong phạm vi hẹp là:

- Object đang ở giai đoạn tái dựng nội bộ, **chưa công bố cho các thành phần/luồng khác**.
- Hoàn tất tất cả cập nhật final field trước khi bất kỳ phần nào đọc những field ấy.
- Sau đó mới cho hệ thống truy cập object đã hoàn chỉnh.

JLS mô tả freeze sau việc sửa final field bằng một số cơ chế đặc biệt, nhưng cũng cảnh báo các phép đọc sau đó có thể bị tối ưu hóa/reorder làm khó dự đoán nếu dùng theo cách tùy tiện. **Không suy ra rằng ghi bằng Reflection sau khi object được sử dụng rộng rãi có semantics giống gán trong constructor**.

### 5.2. Vì sao không nên sửa final field của object đã công bố?

Nếu object đã được chia sẻ cho nhiều luồng, hoặc code đã đọc giá trị final của nó, sau đó một luồng dùng Reflection ghi lại final field, các luồng/code khác có thể đã giữ/hoặc được compiler tối ưu hóa quanh giá trị cũ. Kết quả quan sát có thể không như mong đợi; đây là lý do các API Java cảnh báo việc dùng Reflection để thay đổi final field ngoài quá trình tái dựng có thể cho kết quả khó dự đoán.

Điều này **không thể sửa chỉ bằng việc thêm `volatile` hay gọi `synchronized` một cách tùy tiện** sau hành động bypass; mô hình đúng là ngăn thực thể bất biến bị sửa sau khi nó được sử dụng. Nếu dữ liệu cần thay đổi thường xuyên, dùng trạng thái mutable được đồng bộ và thiết kế API phù hợp từ đầu, hoặc thay cả tham chiếu tới object bất biến mới bằng cơ chế công bố an toàn.

## 6. Bất biến đối tượng không chỉ là tất cả field mang `final`

### 6.1. Field final giữ tham chiếu mutable

Phản mẫu:

```java
final class BadCart {
    private final java.util.List<String> products;

    BadCart(java.util.List<String> products) {
        this.products = products; // Giữ nguyên alias mutable của caller.
    }

    java.util.List<String> products() {
        return products; // Lộ alias mutable ra ngoài.
    }
}
```

Cách khai báo này cho phép caller sửa danh sách đã truyền vào hoặc danh sách trả về, khiến nội dung thay đổi dù `products` là `final`. Sửa bằng `List.copyOf(products)` khi phù hợp (lưu ý shallow copy) và không trả lại cấu trúc mutable có thể sửa từ bên ngoài.

### 6.2. Invariant liên trường

Với khoảng giá trị `start <= end`, không thể coi cập nhật trực tiếp từng field là tương đương tạo một object hợp lệ. Ví dụ:

```java
public record Range(int start, int end) {
    public Range {
        if (start > end) {
            throw new IllegalArgumentException("start > end");
        }
    }

    public Range withEnd(int newEnd) {
        return new Range(start, newEnd);
    }
}
```

Đây là **khai báo độc lập** cho file `Range.java` trong Java 17+. Compact canonical constructor của record luôn kiểm tra quan hệ `start <= end`. `withEnd` tạo record mới và kiểm tra lại. Trường thành phần record là final và không thuộc nhóm mà `Field.set` được phép ghi.

Với object có nhiều field phụ thuộc nhau, code cập nhật cần xử lý cả invariant và trạng thái trung gian. Với immutable data, tạo instance mới thường giúp loại bỏ trạng thái “nửa cập nhật” có thể bị quan sát.

## 7. So sánh các phương án thay đổi dữ liệu

| Nhu cầu | Phương án phù hợp | Vì sao |
| --- | --- | --- |
| Tạo instance lần đầu | Constructor/factory/builder có validation | Có thể bảo đảm object hợp lệ trước khi trả ra |
| Điều chỉnh giá trị trên immutable object | `withX(...)` hoặc factory trả instance mới | Duy trì kiểm tra, giữ object cũ ổn định |
| Thay đổi trạng thái mutable object | Method nghiệp vụ có validation và đồng bộ khi cần | Giữ invariant và kiểm soát tính đồng thời |
| Hiển thị/đọc metadata | `Field.getName`, `getType`, `getModifiers`, `getDeclaringClass` | Có thể phân tích cấu trúc mà không đổi dữ liệu |
| Đọc field khi được phép | `Field.get(receiver)` | Chỉ quan sát dữ liệu; vẫn phải tôn trọng quyền truy cập |
| Framework tái dựng object đặc thù | Cơ chế serialization đã thiết kế riêng, với quy tắc lifecycle và visibility | Chỉ dùng low-level mutation trước khi công bố object và theo giới hạn runtime |
| Sửa trực tiếp private final field của object đang chạy | Tránh; thiết kế lại API cập nhật | Có nguy cơ phá invariant và final-field semantics |

**Lưu ý:** không phải mọi thao tác Reflection đều nguy hiểm hoặc không nên dùng. Lấy metadata, dependency injection hay deserialization có phạm vi hợp lệ nếu tuân theo hợp đồng API/runtime. Bài học cụ thể ở đây là không thay thế vòng đời khởi tạo và luật bất biến bằng việc tự do sửa field.

## 8. Các lỗi nhận thức và hậu quả

| Nhận định sai | Sửa lại cho đúng |
| --- | --- |
| “`Field.set` thành công thì object hợp lệ.” | Reflection không tự chạy validation của constructor/method nghiệp vụ |
| “Tất cả field đều `final` thì object chắc chắn immutable.” | Mutable object bên trong, alias và việc lộ `this` có thể phá an toàn |
| “`setAccessible(true)` luôn vượt mọi quyền truy cập.” | JPMS, loại field, record/hidden class và hạn chế runtime có thể chặn |
| “`final` luôn khiến Reflection không sửa được.” | Một số instance final field trong ordinary class có thể ghi trong điều kiện hẹp |
| “Sửa final field sau khi chia sẻ object sẽ được tất cả luồng thấy giống như cập nhật `volatile`.” | Final-field semantics và tối ưu hóa JIT không cho phép suy luận đó |
| “Serialization cần Reflection nên mọi domain update cũng nên sửa field.” | Tái dựng object trước khi công bố có lifecycle rất khác sửa object đang được sử dụng |
| “Muốn chỉnh một thuộc tính immutable thì sửa field cũ cho đỡ cấp phát.” | Dùng object mới hợp lệ và quản lý việc công bố tham chiếu mới |
| “Một constructor gán field là đủ; không cần kiểm tra liên trường.” | Constructor phải xác minh các invariant cần thiết, kể cả quan hệ giữa các field |

## 9. Quy trình ra quyết định khi gặp một yêu cầu “sửa field”

**Bước 1:** Xác định đây là field instance hay static, `final` hay mutable, của class thường, record hay hidden class.

**Bước 2:** Xác định yêu cầu là đọc metadata, đọc giá trị, tái dựng object từ dữ liệu lưu trữ, hay **cập nhật nghiệp vụ trên object đã tồn tại**. Đây là các mục đích khác nhau.

**Bước 3:** Với cập nhật nghiệp vụ, tìm constructor/factory, getter, `withX` hoặc method cập nhật được thiết kế cho invariant. Nếu chưa có, thiết kế API phù hợp và thêm validation; không để caller tự tiện ghi vào trường private.

**Bước 4:** Nếu dữ liệu có reference mutable, kiểm tra defensive copying và alias. Nếu nhiều luồng có thể truy cập object, xác định cơ chế công bố và đồng bộ trạng thái.

**Bước 5:** Chỉ khi làm công cụ tái dựng/deserialization đặc thù mới xét low-level field mutation; phải đọc hợp đồng `Field.set` của JDK đang dùng, giới hạn module, điều kiện final field và lifecycle “trước khi công bố”. Không tự suy luận từ kết quả một lần chạy hoặc từ một JVM cụ thể.

## 10. Câu hỏi tự kiểm tra

1. `private final List<String> items` có bảo đảm caller không thể sửa nội dung `items` không? Tại sao?
2. Constructor của `Receipt` từ chối `totalCents < 0`. Nếu code khác ghi trực tiếp field thành `-100`, invariant còn đúng không?
3. Tại sao Java Reflection tìm được một private final field bằng `getDeclaredField` mà chưa chắc ghi được bằng `set`?
4. `static final`, record component và instance final field của ordinary class có cùng khả năng ghi bằng `Field.set` không?
5. Vì sao việc Reflection sửa final field sau khi object đã được dùng bởi các luồng không thể coi là cập nhật bình thường?
6. Nếu cần thay `totalCents` của `Receipt` một cách hợp lệ, cách nào được dùng trong chương trình chạy độc lập?

**Đáp án:** (1) không; `final` chỉ cố định tham chiếu, phải ngăn mutable alias; (2) không; (3) tra cứu metadata và kiểm tra quyền ghi là hai giai đoạn khác nhau; (4) không; (5) final-field/JMM semantics và tối ưu hóa cho phép kết quả quan sát không như mong đợi; (6) `original.withTotal(newTotal)` tạo một `Receipt` mới qua constructor.

## 11. Kết luận và tài liệu kỹ thuật

**Constructor và factory là ranh giới tạo ra trạng thái hợp lệ; `final` hỗ trợ thiết kế trạng thái ổn định; Reflection là công cụ truy cập metadata và field theo các quy tắc nghiêm ngặt.** Việc một final instance field có thể bị sửa trong trường hợp đặc biệt không làm cho `Field.set` trở thành API thay thế constructor hoặc phương pháp chỉnh sửa immutable object. Luôn duy trì invariant, kiểm soát alias và lifecycle công bố object trước khi nghĩ tới phép sửa field ở mức thấp.

Tham khảo đặc tả chính thức:

- [Java SE 21 – `java.lang.reflect.Field.set`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Field.html#set(java.lang.Object,java.lang.Object)): điều kiện ghi field và giới hạn đối với final field.
- [Java Language Specification 17 – `17.5 final Field Semantics`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.5): ý nghĩa final field trong Java Memory Model.
- [JLS `17.5.3 – Subsequent Modification of final Fields](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.5.3): trường hợp tái dựng đặc thù và rủi ro khi sửa final field sau constructor.