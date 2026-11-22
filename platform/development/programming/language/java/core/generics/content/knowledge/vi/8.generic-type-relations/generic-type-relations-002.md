# Vì sao `List<Integer>` không phải `List<Number>`? Chọn cách xử lý đúng

**`Integer extends Number` không kéo theo `List<Integer> extends List<Number>`.** Java Generics bất biến (*invariant*) đối với đối số kiểu cụ thể: một `List<Integer>` không thể tự được sử dụng như `List<Number>`, mặc dù từng Integer vẫn có thể dùng như một Number.

Bài này trả lời câu hỏi **“khi đang có `List<Integer>` mà API muốn xử lý Number, tôi thực sự cần làm gì?”** bằng cách phân biệt ba kết quả: *chỉ đọc dữ liệu*, *ghi vào nơi nhận dữ liệu*, và *sở hữu một List<Number> thật sự*. Mỗi nhu cầu đòi một chữ ký khác nhau; thay vì viết nhiều phép ép kiểu, ta chuyển đổi **thiết kế API hoặc cấu trúc lưu trữ**.

## 1. Phép gán nào hợp lệ, phép gán nào không?

Xét:

~~~java
Integer n = 7;
Number number = n; // Hợp lệ: Integer là subtype của Number.

List<Integer> ids = List.of(10, 20);

// List<Number> direct = ids; // LỖI BIÊN DỊCH.
List<? extends Number> view = ids; // Hợp lệ.
~~~

Khi thấy lỗi `incompatible types: List<Integer> cannot be converted to List<Number>`, cần tách hai câu hỏi:

1. **Phần tử có dùng được như Number không?** Có. Integer là subtype của Number.
2. **Toàn bộ danh sách có thể hứa mọi quyền của List<Number> không?** Không. List<Number> cho phép `add(3.5)`, trong khi List<Integer> không thể chấp nhận một Double.

Nếu một biến List<Number> được phép tham chiếu List<Integer>, code khác sẽ có thể đưa Double vào danh sách mà caller vốn kỳ vọng chỉ có Integer. Java từ chối **phép gán nguy hiểm ngay lúc biên dịch**, bảo toàn mối quan hệ giữa kiểu phần tử được ghi vào và kiểu mà `get` hứa trả ra.

Điều cấm này không phụ thuộc danh sách hiện rỗng hay đã có dữ liệu. Một `List<Integer>` có thể đang immutable, nhưng *invariance* và *immutability* vẫn là hai khái niệm độc lập.

## 2. Trước khi sửa lỗi, hãy xác định mục tiêu thật sự

| Nhu cầu thực tế | Lựa chọn đúng | Có tạo list mới? |
| --- | --- | --- |
| Chỉ tính toán/đọc như Number | `Collection<? extends Number>` hoặc `List<? extends Number>` | Không |
| Chỉ duyệt phần tử không cần chỉ số | `Iterable<? extends Number>` | Không |
| Đưa các Integer vào một đích do người gọi sở hữu | `Collection<? super Integer>` | Không bắt buộc |
| Có list mới chứa được cả Integer và Double | `List<Number> copy = new ArrayList<>(ids)` | Có |
| Chỉ muốn đếm phần tử của mọi loại List | `List<?>` | Không |
| Cần đọc–ghi nhất quán một kiểu chính xác do caller định | `List<T>` trong generic method | Không bắt buộc |
| Một API *thực sự* cần list có type argument Number | Tạo/duy trì một `List<Number>` | Tùy API |

Hai lựa chọn dễ gây nhầm nhất là **góc nhìn để đọc `List<? extends Number>`** và **danh sách thật `List<Number>`**. Góc nhìn không chuyển đổi hay sao chép object. Bản sao tạo ra collection mới, có thể thêm những loại Number khác mà không làm thay đổi danh sách Integer gốc.

## 3. Trường hợp A — Method chỉ cần đọc Number

Một method tính tổng không cần biết danh sách chứa Integer, Double hay Long:

~~~java
static double average(Collection<? extends Number> source) {
    double total = 0;
    int count = 0;

    for (Number value : source) {
        total += value.doubleValue();
        count++;
    }

    return count == 0 ? 0 : total / count;
}
~~~

`? extends Number` mang nghĩa **một type argument cụ thể chưa biết**, nhưng chắc chắn nằm trong họ Number. Khi duyệt, mỗi giá trị có thể dùng như Number.

Nhiều loại nguồn hợp lệ:

~~~java
average(List.of(10, 20));   // Có thể nhận List<Integer>.
average(List.of(1.5, 2.5)); // Có thể nhận List<Double>.
~~~

Chữ ký `Collection<? extends Number>` tổng quát hơn `List<? extends Number>` nếu method không cần `get(index)`, vì nó dùng được với nhiều collection implementations hơn. Khi chỉ cần iteration, `Iterable<? extends Number>` còn rộng hơn; chọn abstraction thấp nhất đủ hỗ trợ thao tác của thuật toán.

### Vì sao không dùng `List<Number>` cho hàm chỉ đọc?

~~~java
static double sumTooStrict(List<Number> values) {
    double total = 0;
    for (Number n : values) {
        total += n.doubleValue();
    }
    return total;
}

// List<Integer> ids = List.of(10, 20);
// sumTooStrict(ids); // LỖI: method đòi List<Number>.
~~~

Đây là một **hợp đồng quá chặt** so với nhiệm vụ thực tế: method không gọi `add`, nhưng yêu cầu một list mà về mặt kiểu **có thể** nhận mọi Number. Sửa chữ ký của method nếu bạn sở hữu API đó, thay vì sao chép các giá trị chỉ để vượt qua sự bất biến.

### Cận trên vẫn không cho thêm số bất kỳ

~~~java
List<Integer> ids = new ArrayList<>(List.of(10, 20));
List<? extends Number> readable = ids;

Number first = readable.get(0); // Hợp lệ.
// readable.add(30);             // LỖI BIÊN DỊCH.
// readable.add(2.5);            // LỖI BIÊN DỊCH.
~~~

Compiler không biết type argument được dấu `?` đại diện chính xác là Integer, Double hay Number. Vì vậy một Number hay Integer tùy ý **không được bảo đảm là loại có thể ghi vào** danh sách đó. `add(null)` có thể hợp lệ về kiểu nhưng còn phụ thuộc khả năng sửa đổi và chính sách null của implementation.

## 4. Trường hợp B — Method cần đưa Integer vào đích rộng hơn

Đây là chiều ngược lại:

~~~java
static void appendIds(
        Collection<? super Integer> destination,
        Collection<Integer> ids) {

    for (Integer id : ids) {
        destination.add(id);
    }
}
~~~

`? super Integer` cho phép đích có type argument Integer, Number hoặc Object. Một Integer có thể được đưa vào bất kỳ danh sách nào trong ba loại đó mà vẫn giữ đúng contract.

~~~java
List<Integer> ids = List.of(10, 20);
List<Object> audit = new ArrayList<>();

appendIds(audit, ids);
System.out.println(audit); // [10, 20]
~~~

Nhưng nếu đọc qua biến `Collection<? super Integer>`/`List<? super Integer>`, element chỉ được bảo đảm dưới kiểu Object. Một đích `List<Object>` hoàn toàn có thể chứa String hoặc những đối tượng khác do các thành phần khác thêm vào.

**PECS** (*Producer Extends, Consumer Super*) là tên gợi nhớ cho thiết kế một chiều này: producer cấp dữ liệu thì dùng upper wildcard, consumer nhận dữ liệu thì dùng lower wildcard. Nó không phải mệnh lệnh đặt wildcard ở mọi tham số.

Khi cần copy **bất kỳ loại T phù hợp** từ nguồn sang đích, thư viện hay viết generic method:

~~~java
static <T> void appendAll(
        Collection<? extends T> source,
        Collection<? super T> destination) {

    for (T item : source) {
        destination.add(item);
    }
}
~~~

Tại một lời gọi, compiler suy luận T sao cho nguồn cấp được giá trị T và đích nhận được T. Với List<Integer> nguồn và List<Number> đích, thao tác đó an toàn và không cần biến List<Integer> thành List<Number>.

## 5. Trường hợp C — Cần tạo `List<Number>` thật sự

Khi bạn thật sự **cần sở hữu** một danh sách cho phép lưu các kiểu Number khác nhau, hãy tạo collection mới:

~~~java
List<Integer> ids = List.of(10, 20);

List<Number> report = new ArrayList<>(ids);
report.add(2.5); // Hợp lệ: list đích có type argument Number.

System.out.println(report); // [10, 20, 2.5]
System.out.println(ids);    // [10, 20]
~~~

Constructor `ArrayList(Collection<? extends E>)` nhận các phần tử từ nguồn có kiểu tương thích E. Trong ví dụ này, context của vế trái xác định E là Number, nên constructor có thể copy Integer sang List<Number>.

**Đây không phải type cast.** Nó tạo một list object mới; hai list không có chung cấu trúc add/remove/set. Nếu element là mutable object, phép copy của ArrayList vẫn là **shallow copy** ở mức tham chiếu element. Với Integer (immutable), ta không gặp vấn đề nội dung phần tử bị đổi qua alias, nhưng không nên khái quát rằng copy này sao chép sâu mọi object.

Nếu cần một collection ban đầu trống chứa các loại số khác nhau:

~~~java
List<Number> numbers = new ArrayList<>();
numbers.add(1);
numbers.add(2.5);
~~~

Cách này diễn đạt ý định **sở hữu list hỗn hợp Number** rõ hơn dùng raw cast để “nâng cấp” List<Integer> đã có.

### Khi nào cần sửa chữ ký, khi nào cần sao chép?

- **Bạn kiểm soát method chỉ đọc**: thay `List<Number>` bằng `List<? extends Number>` thường tối ưu và không copy.
- **Bạn kiểm soát method chỉ nhận Integer**: nhận `List<? super Integer>` khi phù hợp với các thao tác.
- **Bạn không kiểm soát một API yêu cầu chính xác `List<Number>`**: tạo `List<Number>` riêng để thích nghi với API.
- **Bạn cần giữ và sửa hai collection độc lập**: copy là quyết định về **ownership**, không đơn thuần là chữa lỗi compiler.
- **Bạn thật sự cần trao đổi phần tử hai chiều**: dùng một named type parameter T phù hợp; two independent wildcards không hứa các element types trùng nhau.

## 6. Một chi tiết suy luận kiểu dễ gây bất ngờ: target typing

Hai biểu thức sau cần được phân biệt:

~~~java
List<Integer> ids = List.of(1, 2);

// List<Number> wrong = ids; // Lỗi: biến ids đã có type List<Integer>.

List<Number> directFactory = List.of(1, 2); // Hợp lệ.
~~~

Vì sao dòng cuối hợp lệ? Lời gọi generic factory `List.of` có thể được compiler suy luận theo **target type** của vế trái, chọn E=Number; những Integer được cung cấp đều phù hợp với Number. Điều đó **không khiến `List<Integer>` đã tồn tại bỗng trở thành `List<Number>`**.

Lưu ý `List.of` trả danh sách **không cho sửa**. Viết `List<Number> directFactory = List.of(1, 2)` không có nghĩa gọi `directFactory.add(2.5)` sẽ chạy được. Đây là vấn đề runtime mutability, khác hẳn tính bất biến *invariance* của generics.

Nếu cần `List<Number>` sửa được từ nguồn Integer, `new ArrayList<>(ids)` là lựa chọn rõ ràng hơn.

## 7. Chương trình Java 17 hoàn chỉnh: ba hướng xử lý

Lưu thành **NumberListMigrationDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

public class NumberListMigrationDemo {
    static double average(Collection<? extends Number> source) {
        double total = 0;
        int count = 0;

        for (Number value : source) {
            total += value.doubleValue();
            count++;
        }
        return count == 0 ? 0 : total / count;
    }

    static void appendIds(
            Collection<? super Integer> destination,
            Collection<Integer> ids) {
        for (Integer id : ids) {
            destination.add(id);
        }
    }

    static List<Number> copyAsNumbers(
            Collection<? extends Number> source) {
        List<Number> answer = new ArrayList<>();
        answer.addAll(source);
        return answer;
    }

    public static void main(String[] args) {
        List<Integer> ids = List.of(10, 20);

        System.out.println("average=" + average(ids));

        List<Number> report = copyAsNumbers(ids);
        report.add(2.5);
        System.out.println("report=" + report);
        System.out.println("original=" + ids);

        List<Object> audit = new ArrayList<>();
        appendIds(audit, ids);
        System.out.println("audit=" + audit);

        List<Number> targetTyped = List.of(1, 2);
        System.out.println("targetTyped=" + targetTyped);
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -Xlint:all NumberListMigrationDemo.java
java NumberListMigrationDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
average=15.0
report=[10, 20, 2.5]
original=[10, 20]
audit=[10, 20]
targetTyped=[1, 2]
~~~

Giải thích:
- `average(ids)` nhận List<Integer> mà không copy nhờ wildcard chỉ đọc.
- `copyAsNumbers(ids)` xây List<Number> mới; thêm Double chỉ sửa list mới.
- `appendIds(audit, ids)` ghi Integer vào List<Object> nhờ cận dưới.
- `targetTyped` chứng minh factory `List.of` có thể dùng target typing để tạo một expression kiểu List<Number>; nó vẫn là list không hỗ trợ add/set.

### Một caveat toán học

`average` chuyển Number sang `double`, do đó có thể mất độ chính xác với những số nguyên rất lớn hoặc những yêu cầu tài chính. **Sự phù hợp về type bounds không bảo đảm độ chính xác số học**. Nếu xử lý tiền tệ, thường nên thiết kế miền dữ liệu và phép cộng bằng BigDecimal/kiểu thích hợp.

Hàm trả 0 cho collection rỗng theo **chính sách minh họa**. Một API production có thể ném exception hoặc trả OptionalDouble thay vì quy ước đó; điều này độc lập với invariance.

## 8. Kiểm thử lỗi biên dịch trước khi sửa API

Các trường hợp sau được viết để **đọc lỗi**, không chèn cùng chương trình chạy:

~~~java
List<Integer> ids = List.of(10, 20);

// List<Number> a = ids;          // Sai: invariant List<E>.
// List<Object> b = ids;          // Sai: invariant List<E>.

List<? extends Number> readable = ids;
// readable.add(30);             // Sai: captured subtype chưa biết.

List<? super Integer> writable = new ArrayList<Number>();
writable.add(30);                 // Đúng.
// Integer x = writable.get(0);   // Sai: đọc chỉ được đảm bảo Object.

List<Number> independent = new ArrayList<>(ids);
independent.add(3.5);             // Đúng: list Number riêng.
~~~

**Không sửa bằng raw/unchecked cast** như `(List<Number>) (List<?>) ids`. Phép cast không đổi kiểu phần tử mà collection thật sự cam kết, và có thể cho phép thêm Double vào list mà code khác đọc như Integer. Một giải pháp đúng phải giữ quan hệ type ở compile time hoặc tạo collection mới với type argument thích hợp.

## 9. Bảng lựa chọn cuối bài

| Câu hỏi bạn đang gặp | Hướng giải quyết |
| --- | --- |
| `sum(List<Number>)` không nhận `List<Integer>` | Sửa API thành `List<? extends Number>` nếu chỉ đọc. |
| Muốn lưu Integer vào `List<Number>` hay `List<Object>` | Nhận `List<? super Integer>` nếu method chỉ ghi Integer. |
| Cần trộn Integer, Double, Long trong một danh sách | Khởi tạo/copy thành `List<Number>` thật. |
| Muốn đếm `List<String>` và `List<Integer>` | Dùng `List<?>`; không cần `List<Object>`. |
| Muốn chuyển collection giữa producer và consumer linh hoạt | Method `<T>` + `? extends T`/`? super T`. |
| Chữ ký đúng nhưng gọi `add` ném UnsupportedOperationException | Xem lại mutability; thay `List.of` bằng một mutable list nếu cần. |
| Thấy `List<Number> x = List.of(1,2)` biên dịch được | Target typing của factory, không phải covariance. |
| Thấy `List<Number> x = existingListOfInteger` không biên dịch | Invariance: hai parameterized types đã được xác định khác nhau. |

## 10. Tự kiểm tra

**Câu 1.** Vì sao `Number value = Integer.valueOf(10)` hợp lệ nhưng `List<Number> values = ids` (ids là List<Integer>) không hợp lệ?

**Đáp án:** Phép gán Number nhận một object Integer là subtype bình thường; trong khi List<Number> còn có quyền add mọi Number mà List<Integer> không thể đáp ứng.

**Câu 2.** Nếu chỉ lấy trung bình từ List<Double> và List<Integer>, nên dùng `List<Number>` hay `List<? extends Number>`?

**Đáp án:** `List<? extends Number>` (hoặc Collection<? extends Number>) vì phương thức chỉ đọc các giá trị tương thích Number.

**Câu 3.** Làm sao tạo list sửa được, nhận cả Integer và Double từ một List<Integer> có sẵn?

**Đáp án:** `List<Number> copy = new ArrayList<>(ints);` rồi thêm Double vào copy. Đây là list object khác, không phải phép ép kiểu.

**Câu 4.** Vì sao `List<Number> x = List.of(1,2)` có thể compile?

**Đáp án:** Generic factory method nhận target typing từ vế trái và suy luận Number; đây không phải phép gán một biến List<Integer> đã định kiểu cho List<Number>.

**Câu 5.** Một generic source có cận extends Number có cho phép tự thêm Integer vào không?

**Đáp án:** Không. Actual subtype của wildcard chưa biết, có thể là Double; chỉ null là ngoại lệ ở mức hệ kiểu, còn mutability là vấn đề riêng.

**Câu 6.** Tại sao muốn cho cả List<Number> lẫn List<Object> nhận Integer, ta dùng `? super Integer`?

**Đáp án:** Cả Number và Object đều là supertypes của Integer, nên cả hai loại collection đều chấp nhận việc ghi Integer.

**Câu 7.** Có nên dùng `List<Number> forced = (List<Number>) (List<?>) ids` để loại lỗi compiler không?

**Đáp án:** Không. Điều đó bỏ qua generic type checking mà không đổi cấu trúc dữ liệu; có thể gây heap pollution và ClassCastException trong code đọc theo kiểu Integer.

**Ghi nhớ:** vấn đề không phải “tìm cú pháp cast để List<Integer> thành List<Number>”, mà là **xác định quyền nào method thực sự cần**. Đọc dữ liệu theo Number thì dùng upper bounded wildcard, ghi Integer thì dùng lower bounded wildcard, còn muốn sở hữu list đa kiểu số thì **tạo List<Number> riêng**.
