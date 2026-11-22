# Ảnh hưởng khi thêm, xóa hoặc thay phần tử trong danh sách nguồn sau `List.copyOf`

**Mục tiêu:** Hiểu chính xác điều gì xảy ra với danh sách do `List.copyOf(source)` trả về khi lập trình viên tiếp tục gọi `add`, `remove`, `set`, đổi thứ tự hoặc thay đổi dữ liệu thông qua một tham chiếu khác đến **danh sách nguồn**.

Từ **Java 10**, `List.copyOf(Collection<? extends E>)` tạo một danh sách **không sửa được** (*unmodifiable list*) chứa các phần tử của collection nguồn theo **thứ tự duyệt tại thời điểm sao chép**. Sau đó, nếu nguồn thay đổi, danh sách kết quả **không phản ánh những thay đổi đó**. Quy tắc này vẫn áp dụng ở các phiên bản Java hiện đại.

Điểm cần phân biệt:

1. **Thay đổi cấu trúc / tham chiếu phần tử của nguồn** — thêm, xóa, thay phần tử, sắp xếp lại: danh sách bản sao không thay đổi.
2. **Thay đổi trạng thái bên trong một đối tượng phần tử được chia sẻ** — chẳng hạn `StringBuilder.append`: bản sao vẫn giữ tham chiếu tới chính đối tượng ấy, nên giá trị quan sát được có thể đổi.
3. **Cố sửa trực tiếp danh sách bản sao** — ném `UnsupportedOperationException`. Đây là hành vi lúc chạy, không phải thông báo lỗi biên dịch.

## 1. Mô hình snapshot: chụp một lần, không đồng bộ hai chiều

~~~java
import java.util.ArrayList;
import java.util.List;

// Các lệnh sau được đặt trong một phương thức:
var source = new ArrayList<>(List.of("A", "B"));
var snapshot = List.copyOf(source);

source.add("C");

System.out.println(source);   // [A, B, C]
System.out.println(snapshot); // [A, B]
~~~

Tại thời điểm `List.copyOf(source)` chạy, `snapshot` ghi nhận **hai phần tử `"A"` và `"B"`**. Phép thêm `"C"` chỉ tác động đến `source`. Bản sao không tự quan sát thay đổi của nguồn.

Có thể hình dung dòng thời gian:

| Thời điểm | Hành động trên nguồn | Nguồn `source` | Bản sao `snapshot` |
| --- | --- | --- | --- |
| T0 | Khởi tạo | `[A, B]` | Chưa có |
| T1 | `List.copyOf(source)` | `[A, B]` | `[A, B]` |
| T2 | `source.add("C")` | `[A, B, C]` | `[A, B]` |
| T3 | `source.remove("A")` | `[B, C]` | `[A, B]` |
| T4 | `source.set(0, "X")` | `[X, C]` | `[A, B]` |

**T1 là mốc chụp dữ liệu**, không phải bắt đầu một mối liên kết để đồng bộ. Vì thế, kích thước, vị trí và danh sách tham chiếu phần tử trong snapshot không thay đổi do các phép sửa của nguồn.

Điều này không phụ thuộc vào việc khai báo kết quả bằng `var snapshot` hay `List<String> snapshot`. `var` chỉ suy luận kiểu tĩnh; cơ chế snapshot thuộc về `List.copyOf`.

## 2. Thêm phần tử vào nguồn: bản sao không nhận phần tử mới

~~~java
var source = new java.util.ArrayList<>(
        java.util.List.of("An", "Bình"));

var snapshot = java.util.List.copyOf(source);
source.add("Chi");
source.add(0, "Đầu");

System.out.println(source);   // [Đầu, An, Bình, Chi]
System.out.println(snapshot); // [An, Bình]
System.out.println(snapshot.size()); // 2
~~~

Cả hai cách thêm, `add(element)` ở cuối và `add(index, element)` ở vị trí xác định, đều chỉ làm danh sách nguồn thay đổi. `snapshot` không có `"Chi"` hay `"Đầu"`.

Danh sách nguồn còn có thể thay đổi qua một tham chiếu khác, ví dụ `var alias = source; alias.add("Thêm");`. Điều đó vẫn không thêm phần tử vào snapshot, vì snapshot không dựa vào cùng cấu trúc danh sách mutable.

Đừng nhầm với:

~~~java
// KHÔNG thêm vào snapshot được:
snapshot.add("Mới"); // Ném UnsupportedOperationException khi chạy
~~~

Dòng trên **biên dịch được** vì giao diện `List` khai báo `add`, nhưng đối tượng do `copyOf` trả về không cho thay đổi.

## 3. Xóa phần tử khỏi nguồn: bản sao không mất phần tử

~~~java
var source = new java.util.ArrayList<>(
        java.util.List.of("A", "B", "A", "C"));

var snapshot = java.util.List.copyOf(source);

source.remove("A"); // Xóa lần xuất hiện đầu tiên của "A"
source.remove(0);   // Xóa phần tử đầu tiên hiện tại của source

System.out.println(source);   // [A, C]
System.out.println(snapshot); // [A, B, A, C]
~~~

`List.copyOf` **giữ nguyên phần tử trùng lặp và thứ tự của `List` nguồn** tại thời điểm sao chép. Trong ví dụ, bản sao vẫn có hai phần tử `"A"`. Một lệnh xóa trên nguồn về sau không tác động đến bản sao, dù lệnh đó xóa đúng đối tượng trước kia cũng có mặt trong bản sao.

Tương tự, các thao tác `source.clear()`, `removeAll(...)`, `removeIf(...)` hoặc thay đổi qua iterator của nguồn (khi collection đó hỗ trợ) không xóa phần tử đã được ghi nhận trong snapshot.

~~~java
source.clear();

System.out.println(source.isEmpty());   // true
System.out.println(snapshot.isEmpty()); // false
~~~

Việc nguồn trở thành rỗng không khiến danh sách đã sao chép rỗng theo.

## 4. Thay phần tử bằng `set`: snapshot giữ tham chiếu cũ

~~~java
var source = new java.util.ArrayList<>(
        java.util.List.of("A", "B", "C"));

var snapshot = java.util.List.copyOf(source);

source.set(1, "NEW");

System.out.println(source);   // [A, NEW, C]
System.out.println(snapshot); // [A, B, C]
System.out.println(snapshot.get(1)); // B
~~~

`set(index, newValue)` thay thế **tham chiếu phần tử ở một vị trí trong danh sách nguồn**. Bản sao không cập nhật tham chiếu tại vị trí đó, nên vẫn giữ `"B"` ban đầu.

Điều này cũng đúng khi sử dụng các thao tác thay thế hàng loạt trên nguồn như `replaceAll(...)`: bản sao không tự nhận các tham chiếu phần tử mới được gán vào danh sách nguồn.

**Lưu ý về kiểu dữ liệu:** `String` là kiểu bất biến, nên ví dụ trên rất trực quan. Với các phần tử có thể sửa đổi, cần tách biệt **thay đối tượng ở vị trí trong list** và **sửa trạng thái của chính đối tượng đang được cả hai list tham chiếu**; phần 6 giải thích cụ thể.

## 5. Sắp xếp hoặc đảo thứ tự nguồn: bản sao giữ thứ tự ban đầu

~~~java
var source = new java.util.ArrayList<>(
        java.util.List.of("C", "A", "B"));

var snapshot = java.util.List.copyOf(source);

java.util.Collections.sort(source);
java.util.Collections.reverse(source);

System.out.println(source);   // [C, B, A]
System.out.println(snapshot); // [C, A, B]
~~~

`List.copyOf` bảo toàn **thứ tự duyệt của nguồn tại thời điểm gọi**, không tiếp tục sắp xếp theo nguồn. Các thao tác `sort`, `reverse`, `swap` hoặc các thay đổi vị trí sau đó không đổi thứ tự của snapshot.

Nếu nguồn là một `Set` hay loại `Collection` không cam kết thứ tự duyệt, `List.copyOf(collection)` vẫn ghi lại thứ tự mà iterator cung cấp lúc sao chép; **không tự suy ra thứ tự chèn hay thứ tự đã sắp xếp**. Trong bài này, với nguồn `ArrayList`, thứ tự là xác định.

## 6. Giới hạn quan trọng: sao chép nông đối với phần tử mutable

**Danh sách snapshot không phản ánh thay đổi cấu trúc nguồn, nhưng đối tượng phần tử vẫn có thể được chia sẻ.** `List.copyOf` không gọi `clone()` hoặc tạo bản sao sâu của từng phần tử.

~~~java
var item = new StringBuilder("old");
var source = new java.util.ArrayList<>(
        java.util.List.of(item));

var snapshot = java.util.List.copyOf(source);

// Sửa TRẠNG THÁI bên trong đối tượng item đã có:
item.append("!");

System.out.println(source.get(0));   // old!
System.out.println(snapshot.get(0)); // old!
~~~

Cả hai danh sách đều đang giữ tham chiếu đến **cùng một `StringBuilder`**. `append("!")` thay đổi đối tượng đó, nên cách hiển thị thông qua cả hai danh sách cùng thay đổi.

Bây giờ thay **phần tử tại vị trí 0 của nguồn**:

~~~java
source.set(0, new StringBuilder("new"));

System.out.println(source.get(0));   // new
System.out.println(snapshot.get(0)); // old!
~~~

Lần này `set` chỉ thay tham chiếu trong danh sách nguồn. Snapshot vẫn trỏ đến đối tượng `StringBuilder` cũ với nội dung `"old!"`.

Bảng so sánh:

| Hành động | Có thay đổi phần tử/thứ tự của `snapshot`? | Có thể thay đổi giá trị đọc từ phần tử mutable? |
| --- | --- | --- |
| `source.add(x)` | Không | Không, nếu không sửa đối tượng đã chia sẻ |
| `source.remove(x)` | Không | Không, nếu không sửa đối tượng đã chia sẻ |
| `source.set(i, x)` | Không | Không do `set`; snapshot giữ tham chiếu cũ |
| `source.sort(...)` | Không | Không do việc đổi vị trí |
| `sharedItem.setSomething(...)` hoặc `append(...)` | Không | **Có**, nếu phần tử được chia sẻ và phương thức thay đổi trạng thái |
| `snapshot.add(x)` / `snapshot.set(i, x)` | Không: thao tác bị từ chối | Không do thao tác bị từ chối |

Vì vậy, khẳng định **“`List.copyOf` làm dữ liệu bất biến hoàn toàn” là sai** đối với các đối tượng phần tử mutable. Nếu cần tính bất biến sâu, hãy dùng phần tử bất biến hoặc tự sao chép phòng vệ từng đối tượng theo yêu cầu nghiệp vụ.

Đối với danh sách `String`, `Integer`, các record có toàn bộ trạng thái bất biến, kết quả thường có thể xem là bất biến hiệu quả ở mức nội dung được quan sát. Nhưng không được suy luận rằng mọi record tự động bất biến sâu: record vẫn có thể chứa tham chiếu tới đối tượng mutable.

## 7. So sánh với `Collections.unmodifiableList(source)`

Cả hai cách đều **không cho người nhận sửa trực tiếp**, nhưng phản ứng khác nhau khi **nguồn** thay đổi:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

// Trong một phương thức:
var source = new ArrayList<>(List.of("A", "B"));

var view = Collections.unmodifiableList(source);
var snapshot = List.copyOf(source);

source.add("C");
source.set(0, "X");

System.out.println(source);   // [X, B, C]
System.out.println(view);     // [X, B, C]
System.out.println(snapshot); // [A, B]
~~~

- `Collections.unmodifiableList(source)` tạo **unmodifiable view** bọc nguồn. Gọi `view.add(...)` bị từ chối, nhưng các phép sửa thông qua `source` vẫn **hiển thị trên view**.
- `List.copyOf(source)` tạo **snapshot không sửa được** của cấu trúc nguồn tại thời điểm gọi. Những sửa đổi về sau của `source` không xuất hiện trên snapshot.

Không dùng `Collections.unmodifiableList` khi mục tiêu là tạo snapshot độc lập với nguồn mutable, và không kỳ vọng `List.copyOf` cập nhật liên tục như một view.

**Chú ý khi nguồn đã là danh sách không sửa được:** `List.copyOf` được phép tái sử dụng instance thích hợp thay vì luôn cấp phát đối tượng mới. Vì vậy không nên kiểm tra `snapshot != source` để kết luận bản sao có đúng hay không. Hợp đồng cần kiểm tra là **nội dung và khả năng không sửa được**, không phải identity.

## 8. Chương trình hoàn chỉnh kiểm chứng từng trường hợp

Lưu tệp **`ListSourceChangesDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class ListSourceChangesDemo {
    public static void main(String[] args) {
        var source = new ArrayList<>(List.of("A", "B", "A"));
        var snapshot = List.copyOf(source);
        var view = Collections.unmodifiableList(source);

        System.out.println("initial=" + snapshot);

        // 1. Thêm vào source.
        source.add("C");
        System.out.println("afterAdd=" + source);
        System.out.println("snapshotAfterAdd=" + snapshot);

        // 2. Xóa phần tử khỏi source.
        source.remove("B");
        System.out.println("afterRemove=" + source);

        // 3. Thay phần tử tại một vị trí của source.
        source.set(0, "X");
        System.out.println("afterSet=" + source);

        // 4. Đổi thứ tự source.
        Collections.swap(source, 0, 2);
        System.out.println("afterSwap=" + source);
        System.out.println("snapshotFinal=" + snapshot);
        System.out.println("viewFinal=" + view);

        // 5. Không được chỉnh sửa trực tiếp snapshot.
        try {
            snapshot.add("Z");
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshotAdd=blocked");
        }
        try {
            snapshot.set(0, "Y");
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshotSet=blocked");
        }

        // 6. Bản sao nông: chia sẻ đối tượng mutable, không chia sẻ
        // cấu trúc list.
        var item = new StringBuilder("old");
        var objectSource = new ArrayList<>(List.of(item));
        var shallow = List.copyOf(objectSource);

        item.append("!");
        System.out.println("mutableElement=" + shallow.get(0));

        objectSource.set(0, new StringBuilder("new"));
        System.out.println(
                "afterObjectReplaceSnapshot=" + shallow.get(0));
        System.out.println(
                "afterObjectReplaceSource=" + objectSource.get(0));

        // 7. List.copyOf không chấp nhận phần tử null.
        try {
            List.copyOf(Arrays.asList("ok", null));
        } catch (NullPointerException ex) {
            System.out.println("null=blocked");
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17+** (các API và cú pháp trong mã tương thích Java 10 trở lên):

~~~bash
javac ListSourceChangesDemo.java
java ListSourceChangesDemo
~~~

**Kết quả `stdout` chính xác:**

~~~text
initial=[A, B, A]
afterAdd=[A, B, A, C]
snapshotAfterAdd=[A, B, A]
afterRemove=[A, A, C]
afterSet=[X, A, C]
afterSwap=[C, A, X]
snapshotFinal=[A, B, A]
viewFinal=[C, A, X]
snapshotAdd=blocked
snapshotSet=blocked
mutableElement=old!
afterObjectReplaceSnapshot=old!
afterObjectReplaceSource=new
null=blocked
~~~

Cách đọc:

1. `snapshot` luôn giữ ba phần tử `[A, B, A]` và **giữ cả phần tử trùng**, bất kể nguồn đã thêm, xóa, thay hay đổi vị trí.
2. `view` phản ánh trạng thái cuối của nguồn `[C, A, X]` vì chỉ là unmodifiable view.
3. Các lời gọi `add`/`set` trực tiếp trên snapshot ném `UnsupportedOperationException`; chương trình bắt ngoại lệ để tiếp tục.
4. `StringBuilder` cũ được snapshot giữ tham chiếu, nên sau `append` nó hiển thị `old!`. Thay phần tử của `objectSource` bằng một đối tượng mới không làm snapshot đổi sang đối tượng mới.
5. Việc nguồn chứa `null` tại thời điểm `List.copyOf` gây `NullPointerException`.

Kết quả không phụ thuộc thứ tự duyệt không xác định: nguồn chính là `ArrayList` với thứ tự đã biết.

## 9. Tạo bản sao mới sau khi nguồn thay đổi

`List.copyOf` **không tự làm mới snapshot cũ**. Nếu muốn lấy trạng thái mới, cần gọi lại:

~~~java
var source = new java.util.ArrayList<>(
        java.util.List.of("A", "B"));

var first = java.util.List.copyOf(source); // [A, B]

source.add("C");

var second = java.util.List.copyOf(source); // [A, B, C]

System.out.println(first);  // [A, B]
System.out.println(second); // [A, B, C]
~~~

`first` và `second` ghi nhận **hai thời điểm khác nhau**. Việc tạo snapshot thứ hai không làm snapshot thứ nhất thay đổi.

Khi code cần xuất bản danh sách mới mỗi lần dữ liệu cập nhật, có thể giữ các bản snapshot khác nhau và chọn bản muốn dùng. Tránh gọi `copyOf` liên tục trong từng vòng lặp chỉ để đọc khi dữ liệu không cần snapshot mới, vì sao chép nguồn mutable lặp lại sẽ tạo chi phí không cần thiết.

## 10. Vấn đề thực tế: `null`, dữ liệu trùng, kiểu nguồn và tính nhất quán

### Nguồn hoặc phần tử `null`

~~~java
// Các đoạn sau minh họa trường hợp không hợp lệ:
// List.copyOf(null); // NullPointerException
// List.copyOf(Arrays.asList("A", null)); // NullPointerException
~~~

Hàm không chấp nhận **collection nguồn là `null`** hoặc có **bất kỳ phần tử `null`** tại lúc gọi. Nếu thêm `null` vào nguồn **sau khi** đã tạo snapshot hợp lệ, snapshot cũ không đột nhiên chứa `null`; nhưng lời gọi `List.copyOf(source)` mới sẽ thất bại nếu nguồn còn phần tử null.

### Phần tử trùng và thứ tự

`List.copyOf` giữ nguyên tất cả phần tử (kể cả các phần tử bằng nhau), đúng theo thứ tự duyệt nguồn ở thời điểm sao chép. Không có bước loại trùng như `Set`. Do đó, thay đổi nguồn làm tăng/giảm số lần xuất hiện của phần tử về sau **không** làm số lần xuất hiện trong snapshot cũ thay đổi.

Nếu đầu vào là `Collection` với thứ tự duyệt không ổn định, thứ tự snapshot phản ánh thứ tự lần sao chép thực tế. Đối với ứng dụng cần sắp xếp xác định, hãy chuyển thành nguồn có thứ tự rõ ràng trước khi gọi `copyOf`.

### Thay đổi đồng thời khi đang sao chép

Cam kết snapshot ở đây áp dụng cho trường hợp nguồn được sao chép trong một trạng thái hợp lệ, ổn định. `List.copyOf` **không phải công cụ đồng bộ đa luồng**. Nếu một luồng khác sửa nguồn đồng thời trong lúc `copyOf` đang duyệt, không nên tự giả định nhận được một bản chụp nguyên tử/nhất quán; hành vi phụ thuộc vào collection và các quy tắc về truy cập đồng thời của nó.

Khi cần snapshot nhất quán trong môi trường đa luồng, hãy đồng bộ hóa truy cập nguồn theo giao thức dùng chung hoặc chọn cấu trúc dữ liệu/cơ chế snapshot phù hợp. Sau khi tạo xong, bản thân list không sửa được vẫn **không làm cho các đối tượng phần tử mutable trở nên an toàn đa luồng**.

## 11. Áp dụng để bảo vệ dữ liệu trong API

Nếu constructor nhận danh sách từ bên ngoài rồi giữ nguyên tham chiếu, người gọi có thể tiếp tục thay đổi danh sách đó và ảnh hưởng đến trạng thái bên trong lớp. `List.copyOf` là một lựa chọn **defensive copy** phù hợp khi chỉ cần chụp cấu trúc danh sách và các phần tử là bất biến.

~~~java
import java.util.List;

public final class CourseCatalog {
    private final List<String> courses;

    public CourseCatalog(List<String> input) {
        // Chụp tại thời điểm xây dựng đối tượng.
        this.courses = List.copyOf(input);
    }

    public List<String> courses() {
        return courses; // Không cho người gọi sửa trực tiếp.
    }
}
~~~

Đây là **lớp ví dụ độc lập không có phương thức `main`**. Giả sử truyền `ArrayList<String>` vào constructor, sau đó `input.add(...)`, `input.remove(...)` hoặc `input.set(...)`, trường `courses` không thay đổi do các thao tác ấy. Ngoài ra, người gọi nhận kết quả từ `courses()` cũng không thể thay đổi danh sách bằng `add`/`set`.

Với `String`, tính bất biến của phần tử hỗ trợ mục tiêu bảo vệ dữ liệu. Nếu khóa học được lưu trong các đối tượng mutable như `Course` có setter, `List.copyOf` không ngăn các setter này làm thay đổi trạng thái được quan sát. Khi đó, cần cân nhắc thiết kế phần tử bất biến hoặc sao chép riêng từng đối tượng.

## 12. Lỗi thường gặp và cách sửa

| Hiểu nhầm / lỗi | Thực tế | Cách xử lý |
| --- | --- | --- |
| “Thêm vào source thì snapshot nhận luôn phần tử mới.” | Sai, snapshot giữ trạng thái lúc tạo. | Tạo snapshot mới khi cần trạng thái mới. |
| “`source.remove` hoặc `source.clear` làm mất phần tử trong snapshot.” | Sai, cấu trúc snapshot độc lập. | Phân biệt nguồn và bản sao. |
| “`source.set(i, x)` thay phần tử ở cùng vị trí trong snapshot.” | Sai, snapshot giữ tham chiếu cũ. | Xác định thời điểm chụp và tham chiếu được lưu. |
| “Đã gọi `List.copyOf` thì mọi giá trị quan sát đều bất biến sâu.” | Sai với phần tử mutable. | Dùng phần tử bất biến hoặc defensive copy sâu. |
| “`List.copyOf` giống hệt `Collections.unmodifiableList(source)`.” | Không: view bám nguồn, snapshot không bám sửa đổi nguồn. | Chọn API theo nhu cầu cập nhật hay snapshot. |
| “`List.copyOf` luôn cấp phát một object mới.” | Không bảo đảm; có thể dùng lại instance phù hợp. | Không phụ thuộc `==`; kiểm tra hành vi. |
| “Có thể thêm `null` vào snapshot.” | Không: tạo copy từ nguồn chứa null ném NPE, sửa snapshot bị chặn. | Kiểm tra/loại null trước khi sao chép, hoặc chọn mô hình dữ liệu thích hợp. |
| “Snapshot có thể tạo nhất quán dù nhiều thread sửa source đồng thời.” | Không có bảo đảm chung như vậy. | Đồng bộ thao tác truy cập/sao chép nguồn. |

## 13. Bài tập tự kiểm tra

### Bài 1 — Tính giá trị sau các thao tác

~~~java
var source = new java.util.ArrayList<>(
        java.util.List.of("red", "green", "blue"));
var copy = java.util.List.copyOf(source);

source.add("yellow");
source.remove("green");
source.set(0, "black");

System.out.println(source);
System.out.println(copy);
~~~

**Đáp án:** Nguồn in `[black, blue, yellow]`; bản sao in `[red, green, blue]`. Việc xóa, thêm, thay thế ở nguồn không tác động đến bản sao.

### Bài 2 — Biến mutable và thay tham chiếu

~~~java
var builder = new StringBuilder("A");
var source = new java.util.ArrayList<>(
        java.util.List.of(builder));
var copy = java.util.List.copyOf(source);

builder.append("B");
source.set(0, new StringBuilder("C"));

System.out.println(source.get(0));
System.out.println(copy.get(0));
~~~

**Đáp án:** Nguồn in `C`, bản sao in `AB`. Bản sao vẫn giữ đối tượng cũ, và đối tượng cũ đã được sửa nội dung trước đó.

### Bài 3 — Chọn đúng công cụ

Một API cần trả về trạng thái tại thời điểm truy vấn, bất kể bên gọi vẫn giữ danh sách gốc và tiếp tục cập nhật. **Nên chọn `List.copyOf` hay `Collections.unmodifiableList(source)`?**

**Đáp án:** Chọn `List.copyOf(source)` (giả định nguồn phù hợp và việc sao chép diễn ra an toàn) để chụp snapshot. `Collections.unmodifiableList` là view phản ánh thay đổi từ nguồn, không đáp ứng yêu cầu “trạng thái tại thời điểm truy vấn”.

## 14. Ghi nhớ

- `List.copyOf(source)` chụp các phần tử **theo thứ tự duyệt và đúng số lần xuất hiện ở thời điểm gọi**.
- **`add`, `remove`, `set`, `sort`, `clear` hoặc thay đổi cấu trúc qua tham chiếu khác của nguồn sau đó không làm snapshot thay đổi**.
- Muốn lấy dữ liệu mới của nguồn, **gọi `List.copyOf` lần nữa** để tạo snapshot tại thời điểm mới.
- `List.copyOf` trả về danh sách **không cho sửa trực tiếp** (mutator gây `UnsupportedOperationException`).
- **Snapshot cấu trúc không đồng nghĩa deep copy**: đối tượng phần tử mutable vẫn có thể đổi trạng thái.
- **`Collections.unmodifiableList(source)` là view**, có thể phản ánh thay đổi nguồn; đừng nhầm với snapshot.
- Tránh giả định identity, khả năng chấp nhận `null` hoặc an toàn đồng thời mà API không cam kết.

### Tài liệu tham khảo chính thức

- [Java SE 26 — `List.copyOf(Collection)`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): hợp đồng không phản ánh sửa đổi nguồn về sau; không nhận null; `Since: 10`.
- [Oracle — Secure Coding Guidelines for Java SE](https://www.oracle.com/java/technologies/javase/seccodeguide.html): phân biệt unmodifiable copies với unmodifiable views trong thiết kế API.
