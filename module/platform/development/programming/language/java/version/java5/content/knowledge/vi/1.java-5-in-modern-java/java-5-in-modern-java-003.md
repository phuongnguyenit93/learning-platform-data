# Mối liên hệ giữa generics, collections, boxing và vòng lặp for-each

## 1. Bốn cơ chế cùng tham gia một dòng mã

Xét một danh sách điểm số và phép tính tổng:

```java
List<Integer> scores = new ArrayList<>();
scores.add(80);
scores.add(95);
int total = 0;
for (int score : scores) {
    total += score;
}
```

Đây là đoạn minh họa trong một phương thức, cần import `java.util.List` và `java.util.ArrayList`. Đằng sau cú pháp gọn có bốn vai trò khác nhau:

| Cơ chế | Vai trò trong ví dụ |
| --- | --- |
| Collection | Giữ và cung cấp cách truy cập nhóm phần tử |
| Generics | Gắn hợp đồng kiểu `Integer` cho phần tử của `List` |
| Boxing/unboxing | Kết nối giá trị `int` với kiểu bao `Integer` |
| Vòng lặp for-each | Lần lượt lấy phần tử để xử lý |

Chúng phối hợp, nhưng không thay thế nhau. Có collection không phải dữ liệu số, có generics ngoài collections, có boxing mà không dùng vòng lặp, và for-each còn duyệt được mảng.

## 2. Collections giữ đối tượng; generics mô tả kiểu phần tử

`List<E>` mô tả danh sách có thứ tự, có truy cập theo vị trí. `ArrayList<E>` là một triển khai thường dùng. Khi viết `List<Integer>`, tham số `E` được thay bằng `Integer` trong hợp đồng kiểu mà trình biên dịch kiểm tra.

Nhờ đó, `scores.add(80)` hợp lệ sau chuyển đổi boxing, còn `scores.add("80")` không biên dịch. Khi đọc `scores.get(0)`, mã gọi nhận `Integer` mà không cần tự viết phép ép kiểu.

Generics không biến `ArrayList` thành nơi lưu `int` nguyên thủy. Trong mô hình generic Java hiện dùng ở đây, đối số kiểu phải là kiểu tham chiếu, nên dùng `List<Integer>`, không có `List<int>`. [List](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html)

`List<String>` và `List<Integer>` cùng dùng hợp đồng danh sách nhưng phục vụ các kiểu phần tử khác nhau. Chọn `List`, `Set` hay `Map` trước hết theo nhu cầu thứ tự, trùng lặp và tra cứu; generics không tự quyết định cấu trúc dữ liệu phù hợp.

## 3. Boxing nối int với Integer

Boxing chuyển giá trị nguyên thủy sang kiểu bao tương ứng, ví dụ `int` sang `Integer`. Unboxing chuyển ngược để dùng trong phép tính. Trong ví dụ mở đầu:

```java
scores.add(80);          // int được boxing thành Integer cho tham số phần tử.
Integer boxed = scores.get(0);
int primitive = boxed;  // Unboxing để lấy int.
```

Có thể hiểu hai chuyển đổi số học cơ bản gần với `Integer.valueOf(80)` và `boxed.intValue()`; không phải yêu cầu mỗi lần boxing đều tạo một đối tượng mới.

Tự động chuyển đổi giúp mã dễ đọc, nhưng không xóa sự khác biệt giữa kiểu bao và nguyên thủy. `Integer` có thể là `null`, còn `int` thì không. Unboxing một tham chiếu `null` gây `NullPointerException`. [JLS: boxing và unboxing](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.7)

Đối với so sánh giá trị hai biến `Integer`, không dựa vào `==` giữa hai tham chiếu: toán tử đó có thể kiểm tra cùng đối tượng. Dùng `equals` hoặc `Objects.equals` nếu cần xử lý `null`. Nếu phép toán có unboxing, phải kiểm soát trường hợp vắng giá trị.

## 4. For-each liên kết với Iterable và kiểu phần tử

`Collection<E>` có khả năng duyệt qua `Iterable<E>`. Vòng lặp for-each trên một collection lần lượt nhận phần tử do iterator cung cấp. Kiểu phần tử generic giúp trình biên dịch kiểm tra biến vòng lặp có nhận được giá trị hay không.

Với `List<Integer>`, hai cách duyệt đều hợp lệ nhưng khác điểm chuyển đổi:

```java
for (Integer score : scores) {
    // Nhận tham chiếu Integer; có thể kiểm tra null trước khi tính.
}

for (int score : scores) {
    // Mỗi phần tử được unboxing để gán vào biến int.
}
```

Đối với `int[]`, for-each lấy trực tiếp các giá trị `int`; không cần boxing chỉ vì dùng cú pháp for-each. Mảng không phải `Iterable`, nhưng được ngôn ngữ hỗ trợ riêng. [JLS: enhanced for](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.14.2)

For-each không tự bảo đảm thứ tự tăng dần hoặc thứ tự chèn; nó theo cách duyệt của nguồn. `List` có thứ tự rõ ràng, còn một cấu trúc khác có thể không có cam kết tương tự. [Iterable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Iterable.html)

## 5. Luồng kiểu từ thêm phần tử đến tính tổng

```text
80: int
   → boxing
Integer
   → add vào List<Integer>
phần tử Integer được duyệt
   → unboxing khi biến vòng lặp là int
score: int
   → cộng vào total
```

Generics hoạt động trong kiểm tra kiểu và hợp đồng mã nguồn; boxing/unboxing là các chuyển đổi giữa giá trị nguyên thủy và kiểu bao; for-each tổ chức việc duyệt. Tính an toàn về kiểu không đồng nghĩa dữ liệu luôn khác `null` hoặc danh sách không thể thay đổi.

Ví dụ `ArrayList<Integer>` có thể chứa `null`, còn `List.of(...)` tạo danh sách không cho sửa cấu trúc và từ chối `null`. Chính API tạo collection quyết định các khả năng này, không phải một mình dấu `<Integer>`.

## 6. Chương trình chạy được: tổng, null và overload remove

Lưu thành `CollectionFeaturesDemo.java`. Ví dụ dùng `List.of` để tạo dữ liệu ban đầu theo Java hiện đại và `ArrayList` khi cần thay đổi nội dung.

```java
import java.util.ArrayList;
import java.util.List;

public class CollectionFeaturesDemo {
    static int sum(Iterable<Integer> values) {
        int total = 0;
        for (int value : values) {
            total += value;
        }
        return total;
    }

    public static void main(String[] args) {
        List<Integer> scores = new ArrayList<>(List.of(80, 95, 70));
        System.out.println("total=" + sum(scores));

        for (int score : scores) {
            score += 5;
        }
        System.out.println("afterLocalChange=" + scores);

        List<Integer> numbers = new ArrayList<>(List.of(10, 20, 30));
        numbers.remove(1);
        System.out.println("removeIndex=" + numbers);
        numbers.remove(Integer.valueOf(30));
        System.out.println("removeValue=" + numbers);

        List<Integer> withMissing = new ArrayList<>();
        withMissing.add(5);
        withMissing.add(null);
        try {
            sum(withMissing);
        } catch (NullPointerException ex) {
            System.out.println("nullCannotBeUnboxed");
        }

        int safeTotal = 0;
        for (Integer value : withMissing) {
            if (value != null) {
                safeTotal += value;
            }
        }
        System.out.println("totalIgnoringMissing=" + safeTotal);

        List<Integer> remaining = new ArrayList<>(List.of(80, 95, 70));
        remaining.removeIf(score -> score < 80);
        System.out.println("remaining=" + remaining);

        int[] primitiveScores = {80, 95, 70};
        int arrayTotal = 0;
        for (int score : primitiveScores) {
            arrayTotal += score;
        }
        System.out.println("arrayTotal=" + arrayTotal);
    }
}
```

Chạy với JDK 17 trở lên:

```shell
javac --release 17 CollectionFeaturesDemo.java
java CollectionFeaturesDemo
```

Stdout chính xác:

```text
total=245
afterLocalChange=[80, 95, 70]
removeIndex=[10, 30]
removeValue=[10]
nullCannotBeUnboxed
totalIgnoringMissing=5
remaining=[80, 95]
arrayTotal=245
```

`sum` nhận `Iterable<Integer>` vì chỉ cần duyệt; nó không cần các khả năng riêng như truy cập chỉ số của `List`. Tuy nhiên, hợp đồng của hàm vẫn yêu cầu các phần tử khác `null`. Nhánh `totalIgnoringMissing` minh họa một **chính sách khác** là bỏ phần tử thiếu; không nên tự áp dụng chính sách đó cho mọi phép tổng.

`remove(1)` chọn overload nhận chỉ số `int`, nên xóa phần tử ở vị trí 1. `remove(Integer.valueOf(30))` chọn overload nhận đối tượng để xóa giá trị 30. Tự động boxing không làm hai overload có cùng ý nghĩa.

## 7. Biến vòng lặp không phải ô trong collection

Gán lại `score` trong for-each chỉ đổi biến cục bộ của lượt đó; nó không ghi ngược vào danh sách. Kiểu bao `Integer` cũng bất biến, nên `Integer value` rồi `value++` vẫn không cập nhật phần tử gốc.

Nếu mục tiêu là thay tất cả điểm bằng điểm mới, dùng thao tác nói đúng ý định, ví dụ `scores.replaceAll(score -> score + 5)` trên danh sách sửa được và không có `null`. Với một danh sách đối tượng có trạng thái, gọi phương thức sửa chính đối tượng là một vấn đề khác với gán lại biến tham chiếu.

For-each cũng không phải chỗ để tự thêm/xóa cấu trúc của chính `ArrayList` đang duyệt. Với lọc bỏ phần tử theo điều kiện, `removeIf` thường rõ ràng; nếu cần điều khiển xóa trong lúc duyệt, dùng iterator và thao tác của nó theo hợp đồng. Không dựa vào `ConcurrentModificationException` như cơ chế điều khiển hay bảo đảm an toàn nhiều luồng. [ArrayList](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ArrayList.html)

## 8. Những giả định mà generics không bảo đảm

### Kiểu bao là kiểu con của Number, nhưng danh sách không chuyển kiểu theo cách đó

`Integer` là một kiểu con của `Number`, nhưng `List<Integer>` không phải `List<Number>`. Nếu được gán như vậy, mã nhận `List<Number>` có thể thêm một `Double` vào danh sách vốn được coi là chỉ chứa `Integer`.

Đoạn minh họa không biên dịch:

```java
List<Integer> integers = new ArrayList<>();
// List<Number> numbers = integers; // Không hợp lệ.
```

Khi chỉ đọc số từ nhiều kiểu danh sách, có thể chọn `Iterable<? extends Number>` và xử lý từng `Number` theo yêu cầu. Không ép kiểu để bỏ qua kiểm tra của generics.

### Kiểu phần tử không phải kiểm tra dữ liệu từ mọi nguồn bên ngoài

Khi dữ liệu đi qua phản chiếu, cơ chế giải mã hoặc API làm mất thông tin kiểu, cần kiểm tra tại ranh giới. Generics trong chữ ký không tự chứng minh một dữ liệu JSON, một đối tượng `Object` hay một collection từ nguồn không kiểm soát có nội dung đúng.

## 9. Cú pháp gọn vẫn có chi phí và giới hạn

`List<Integer>` thường lưu các tham chiếu đến kiểu bao, còn `int[]` lưu giá trị nguyên thủy. Với dữ liệu số lớn, boxing có thể ảnh hưởng cấp phát, truy cập bộ nhớ và unboxing. Đừng khẳng định mỗi lần thêm số đều cấp phát mới vì có thể có tái sử dụng đối tượng hoặc tối ưu của JVM.

Trong phép tính số thuần, cân nhắc `int[]`, `IntStream` hoặc công cụ phù hợp khi đo đạc cho thấy cần thiết. `IntStream` là một luồng nguyên thủy, không phải một collection để thay thế mọi nhu cầu lưu trữ/thêm/xóa. [IntStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/IntStream.html)

Cũng không có bảo đảm phép cộng `int` không tràn chỉ vì phần tử đến từ collection có generics. Nếu miền dữ liệu lớn, chọn kiểu tích lũy và chính sách tràn theo nghiệp vụ.

## 10. Tự thực hành

1. Viết hàm nhận `Iterable<String>` để tính tổng độ dài chuỗi, rồi giải thích vì sao không cần boxing số cho phần tử.
2. Thêm một `null` vào `ArrayList<Integer>` và thử hai kiểu biến vòng lặp `Integer`/`int`.
3. So sánh `remove(2)` với `remove(Integer.valueOf(2))` trên một danh sách phù hợp.
4. Dùng `replaceAll` để tăng mỗi điểm 5, rồi so với việc chỉ sửa biến vòng lặp.

Đối chiếu: generics xác định kiểu phần tử, collection xác định cấu trúc và thao tác, boxing nối số nguyên thủy với kiểu bao, còn for-each quyết định cách lấy lần lượt giá trị để xử lý.