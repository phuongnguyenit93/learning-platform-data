# Phối hợp generics, boxing và for-each với collection

Ba tính năng thường xuất hiện cùng nhau trong Java:

```java
List<Integer> scores = new ArrayList<>();
scores.add(10);
scores.add(20);

int total = 0;
for (int score : scores) {
    total += score;
}
```

Đoạn này minh họa bên trong một phương thức, giả sử đã import `List` và `ArrayList`.

Mã ngắn gọn vì mỗi cơ chế giải quyết một phần việc:

1. **Generics** mô tả và kiểm tra kiểu phần tử.
2. **Boxing/unboxing** chuyển giữa giá trị nguyên thủy và kiểu bao.
3. **For-each** cung cấp cách duyệt không cần tự quản lý chỉ số hoặc iterator trong mã viết ra.

Chúng phối hợp với nhau nhưng không thay thế trách nhiệm kiểm tra dữ liệu và chọn đúng thao tác collection.

## 1. Generics xác định kiểu phần tử được dùng qua API

`List<Integer>` biểu thị danh sách có các phần tử được xử lý theo kiểu `Integer` qua API đã khai báo:

```java
List<Integer> scores = new ArrayList<>();
scores.add(10);
Integer first = scores.get(0);

// Không hợp lệ:
// scores.add("ten");
```

Trình biên dịch có thể phát hiện việc thêm chuỗi vào danh sách số mà không chờ đến lúc lấy phần tử ra.

Không viết `List<int>` vì đối số kiểu generic phải là kiểu tham chiếu. Với số nguyên `int`, kiểu bao thông dụng là `Integer`.

`List<Integer>` không có nghĩa là mảng nguyên thủy và không tự bảo đảm:

- Không có phần tử `null`.
- Mọi giá trị đều dương hoặc nằm trong một khoảng nghiệp vụ.
- Collection cho phép thêm/xóa.
- Collection an toàn khi nhiều luồng cùng truy cập.

Các tính chất đó phụ thuộc triển khai và hợp đồng dữ liệu riêng.

### Tránh đánh mất thông tin kiểu

Dùng raw type như `List` không có đối số kiểu có thể làm mất kiểm tra hữu ích và dẫn đến các cảnh báo unchecked. Không bỏ generics chỉ để thêm nhiều kiểu không tương thích vào cùng danh sách.

`List<Integer>` cũng không phải kiểu con của `List<Number>`, dù `Integer` là kiểu con của `Number`. Nếu cần API chỉ đọc nhiều dạng danh sách số, có thể thiết kế với `Iterable<? extends Number>` hoặc một wildcard phù hợp.

Trong trường hợp đó, biến vòng lặp có thể là `Number` rồi gọi rõ `longValue()`, `doubleValue()`... theo yêu cầu; không giả định `Number` tự unboxing thành mọi kiểu nguyên thủy như một biến `Integer`.

## 2. Boxing khi thêm và unboxing khi dùng

Với:

```java
scores.add(10);
```

`10` là literal `int`, còn `add` của `List<Integer>` nhận `Integer`. Java thực hiện boxing để cung cấp giá trị kiểu bao.

Có thể hình dung tại mức ý nghĩa:

```java
scores.add(Integer.valueOf(10));
```

Khi lấy ra để tính toán:

```java
int first = scores.get(0);
```

giá trị `Integer` được unboxing thành `int`.

Không cần tự viết các lời gọi chuyển đổi trong mọi dòng, nhưng cần biết chúng đang xảy ra để giải thích lỗi `null`, lựa chọn overload và chi phí xử lý.

Boxing không đồng nghĩa với chắc chắn tạo một đối tượng mới cho mỗi lần chuyển đổi. Một số giá trị có thể dùng đối tượng đã lưu sẵn và JVM có thể tối ưu. Tuy nhiên, `List<Integer>` vẫn là mô hình collection kiểu tham chiếu, không có cùng cách biểu diễn với `int[]`.

### So sánh giá trị kiểu bao

Không dùng `==` giữa hai biến `Integer` như một quy tắc so sánh giá trị số. Nếu cả hai toán hạng là tham chiếu kiểu bao, `==` so sánh tham chiếu; cơ chế lưu sẵn đối tượng có thể khiến vài ví dụ nhỏ trông đúng và gây hiểu nhầm.

Dùng `equals`, `Objects.equals` hoặc chuyển sang nguyên thủy theo một hợp đồng xử lý `null` rõ ràng.

## 3. For-each lấy từng giá trị qua Iterable

Với collection triển khai `Iterable`, vòng lặp:

```java
for (Integer score : scores) {
    System.out.println(score);
}
```

có thể được hiểu theo cơ chế iterator:

```java
Iterator<Integer> iterator = scores.iterator();
while (iterator.hasNext()) {
    Integer score = iterator.next();
    System.out.println(score);
}
```

Đoạn thứ hai là mô hình tương đương để giải thích, giả sử đã import `Iterator`. Trình biên dịch quản lý biến phụ khi chuyển vòng lặp; không cần tạo tên `iterator` thủ công trong cách viết for-each.

Nếu viết:

```java
for (int score : scores) {
    System.out.println(score);
}
```

thì mỗi `Integer` lấy ra cần unboxing trước khi được gán cho biến `int score`.

Với mảng, for-each dùng cơ chế duyệt mảng thay vì iterator. Cùng cú pháp bề ngoài không có nghĩa collection và mảng có cùng cách lưu trữ hoặc thực thi.

Thứ tự duyệt do nguồn dữ liệu quy định. `ArrayList` duyệt theo thứ tự danh sách; không suy từ đó rằng mọi `Set` hoặc `Queue` đều có cùng quy tắc.

## 4. Null là điểm nối dễ gây lỗi

`ArrayList<Integer>` chấp nhận phần tử `null`. Generics không tự cấm điều đó:

```java
List<Integer> scores = new ArrayList<>();
scores.add(null);
```

Vòng lặp dùng `Integer` có thể nhận `null` và xử lý rõ ràng:

```java
for (Integer score : scores) {
    if (score == null) {
        continue;
    }
    System.out.println(score + 1);
}
```

Nhưng với `for (int score : scores)`, nếu gặp `null`, thao tác unboxing gây `NullPointerException` trước khi thân vòng lặp của lượt đó bắt đầu. Không thể đặt `if (score == null)` bên trong để xử lý vì `score` đã là `int` và bước lỗi xảy ra trước.

Chính sách với dữ liệu thiếu cần có chủ đích: bỏ qua, từ chối hoặc dùng giá trị mặc định theo nghiệp vụ. Ví dụ dưới đây chọn bỏ qua trong phép tính tổng để minh họa, không coi đó là chính sách đúng cho mọi hệ thống.

## 5. Chương trình hoàn chỉnh

Ví dụ dùng Java 17+ để quan sát boxing khi thêm, unboxing khi tính, tạo danh sách kết quả, lỗi null và cách xóa an toàn bằng iterator.

Lưu thành `CollectionFeaturesDemo.java`:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

public class CollectionFeaturesDemo {
    static long sumPresent(Iterable<Integer> values) {
        long sum = 0;
        for (Integer value : values) {
            if (value != null) {
                sum += value;
            }
        }
        return sum;
    }

    public static void main(String[] args) {
        List<Integer> scores = new ArrayList<>();
        scores.add(10);
        scores.add(20);
        scores.add(null);
        scores.add(30);
        System.out.println("scores: " + scores);
        System.out.println("sum present: " + sumPresent(scores));

        List<Integer> doubled = new ArrayList<>();
        for (Integer value : scores) {
            if (value != null) {
                doubled.add(value * 2);
            }
        }
        System.out.println("doubled: " + doubled);

        for (Integer value : scores) {
            value = 0;
        }
        System.out.println("after loop assignment: " + scores);

        try {
            for (int value : scores) {
                if (value < 0) {
                    System.out.println("negative");
                }
            }
        } catch (NullPointerException e) {
            System.out.println("primitive loop: NullPointerException");
        }

        List<Integer> removable = new ArrayList<>(List.of(10, 20, 30));
        System.out.println("remove index 1: " + removable.remove(1));
        System.out.println("after index removal: " + removable);
        System.out.println("remove value 30: "
                + removable.remove(Integer.valueOf(30)));
        System.out.println("after value removal: " + removable);

        Iterator<Integer> iterator = scores.iterator();
        while (iterator.hasNext()) {
            Integer value = iterator.next();
            if (value == null || value < 20) {
                iterator.remove();
            }
        }
        System.out.println("cleaned: " + scores);

        int total = 0;
        for (int value : scores) {
            total += value;
        }
        System.out.println("primitive loop total: " + total);
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 CollectionFeaturesDemo.java
java CollectionFeaturesDemo
```

Stdout:

```text
scores: [10, 20, null, 30]
sum present: 60
doubled: [20, 40, 60]
after loop assignment: [10, 20, null, 30]
primitive loop: NullPointerException
remove index 1: 20
after index removal: [10, 30]
remove value 30: true
after value removal: [10]
cleaned: [20, 30]
primitive loop total: 50
```

### Đọc các cơ chế đang phối hợp

Trong `doubled.add(value * 2)`:

1. `value` có kiểu `Integer`.
2. Phép nhân cần số nguyên thủy nên có unboxing.
3. Kết quả phép nhân là `int`.
4. Thêm vào `List<Integer>` cần boxing kết quả.

Nhánh kiểm tra `value != null` bảo vệ bước unboxing.

Biến `sum` có kiểu `long`, giúp phép cộng trong ví dụ dùng kết quả rộng hơn `int`. Điều này không có nghĩa mọi tổng lớn đều tránh được tràn; thuật toán thực tế vẫn cần chọn kiểu và chính sách tràn số phù hợp.

Sau khi iterator đã loại null và giá trị dưới 20, vòng lặp nguyên thủy ở cuối có thể duyệt hai giá trị 20 và 30 mà không gặp dữ liệu null.

## 6. Gán lại biến vòng lặp không thay phần tử collection

Đoạn:

```java
for (Integer value : scores) {
    value = 0;
}
```

chỉ gán lại biến cục bộ của từng lượt lặp. Nó không gọi `List.set` và không thay ô nào của danh sách. Đây là lý do stdout vẫn có `[10, 20, null, 30]`.

`Integer` là kiểu bất biến; không có thao tác sửa giá trị bên trong chính một đối tượng `Integer` để biến nó thành số khác.

Nếu phần tử là một đối tượng thay đổi được như `Person`, gọi `person.setName(...)` có thể sửa đối tượng mà danh sách đang tham chiếu. Điều đó khác với `person = new Person(...)`, vốn chỉ gán lại biến vòng lặp.

Muốn thay từng phần tử danh sách, hãy dùng thao tác phù hợp như vòng lặp chỉ số với `set`, `ListIterator.set`, `replaceAll` nếu được triển khai hỗ trợ, hoặc tạo danh sách mới như `doubled`.

Không áp dụng vòng lặp chỉ số một cách máy móc cho mọi `List`: gọi `get(i)` nhiều lần trên một danh sách liên kết có thể tốn kém hơn duyệt iterator.

## 7. Boxing làm hai overload remove dễ bị nhầm

`List<Integer>` có hai thao tác liên quan:

```java
Integer remove(int index);     // Với E là Integer.
boolean remove(Object value);
```

Đây là mô tả chữ ký sau khi xem `E` như `Integer`, không phải các khai báo để thêm vào chương trình.

Với `[10, 20, 30]`:

- `remove(1)` chọn tham số `int index`, loại phần tử ở chỉ số 1 là 20.
- `remove(Integer.valueOf(30))` chọn cách xóa theo giá trị đối tượng, loại một phần tử bằng 30 và trả `true`.

`remove(30)` không tự được hiểu là xóa số 30. Nó có thể bị hiểu là chỉ số 30 và gây `IndexOutOfBoundsException`.

Generics không xóa sự tồn tại của overload nhận chỉ số. Khi ý định là xóa theo giá trị số, cung cấp biểu thức kiểu bao tường minh giúp thể hiện rõ ý định.

## 8. Thay đổi cấu trúc trong khi duyệt

Không nên viết vòng for-each rồi trực tiếp thêm/xóa trên cùng một `ArrayList`:

```java
// Minh họa cách dùng không phù hợp:
// for (Integer value : scores) {
//     if (value == null) {
//         scores.remove(value);
//     }
// }
```

For-each đang dùng iterator. Thay đổi cấu trúc ngoài cơ chế iterator có thể khiến iterator fail-fast báo `ConcurrentModificationException`. Không dựa vào việc một ví dụ ngắn tình cờ chưa ném lỗi để kết luận cách dùng được hỗ trợ; cơ chế phát hiện lỗi không phải bảo đảm đồng bộ.

Các lựa chọn tùy nhu cầu:

- Dùng `Iterator.remove` sau `next` như chương trình, khi triển khai hỗ trợ.
- Dùng `removeIf` trên collection cho phép xóa.
- Tạo collection kết quả rồi giữ nguồn để chỉ đọc.

`Iterator.remove` là thao tác tùy chọn, không phải mọi collection đều hỗ trợ. Danh sách không cho sửa có thể từ chối thay đổi bằng `UnsupportedOperationException`.

## 9. Chuyển từ mảng nguyên thủy sang collection

Một cách rõ ràng để tạo danh sách từ `int[]`:

```java
int[] raw = {2, 4, 6};
List<Integer> values = new ArrayList<>();
for (int value : raw) {
    values.add(value);
}
```

For-each ở đây duyệt mảng; `add` thực hiện boxing từng `int` thành `Integer`.

Không giả định `Arrays.asList(raw)` tự tạo `List<Integer>`. Khi `raw` là `int[]`, biểu thức đó có thể tạo danh sách có **một phần tử là chính mảng `int[]`**, không phải ba phần tử kiểu bao.

Chuyển đổi từng giá trị và chuyển đổi toàn bộ kiểu cấu trúc là hai việc khác nhau. Boxing từng `int` không tạo một phép chuyển đổi tự động từ `int[]` sang `Integer[]` hay `List<Integer>`.

## 10. Tự kiểm tra

1. Vì sao dùng `List<Integer>` mà không dùng `List<int>`?
2. Một `ArrayList<Integer>` có thể chứa null không?
3. Với null trong danh sách, lỗi ở `for (int value : list)` xuất hiện trước hay sau khi thân lượt lặp tương ứng bắt đầu?
4. Gán `value = 0` trong for-each có cập nhật danh sách không?
5. Muốn xóa số 1 theo giá trị khỏi `List<Integer>`, nên viết thế nào để tránh hiểu là chỉ số?
6. For-each có tự bảo đảm collection được duyệt theo thứ tự đã sắp xếp không?

Đáp án:

1. Đối số kiểu generic cần kiểu tham chiếu; `Integer` là kiểu bao của `int`.
2. Có; cần kiểm tra hợp đồng của từng triển khai.
3. Trước; bước unboxing để gán biến vòng lặp đã gây lỗi.
4. Không; đó là biến cục bộ.
5. Chẳng hạn `list.remove(Integer.valueOf(1))`.
6. Không; thứ tự do nguồn dữ liệu quy định.

## Tài liệu đối chiếu

Xem [JLS 21 §14.14.2 — Enhanced for](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.14.2), [§5.1.7 — Boxing](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.7), [§5.1.8 — Unboxing](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.8), [List](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html) và [Iterator.remove](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Iterator.html#remove()).
