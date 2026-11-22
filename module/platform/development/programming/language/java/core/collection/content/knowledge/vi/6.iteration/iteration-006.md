# forEach, lambda và giới hạn thay đổi nguồn khi duyệt

`forEach` diễn đạt một yêu cầu đơn giản: **thực hiện một hành động với từng phần tử hoặc từng ánh xạ**. Lambda mô tả hành động đó.

Cú pháp ngắn hơn không làm mất các quy tắc của quá trình duyệt. Đặc biệt, một lambda có thể biên dịch được nhưng vẫn sửa nguồn dữ liệu theo cách không được bảo đảm.

Để dùng đúng, cần phân biệt:

- Duyệt nguồn để tạo tác dụng bên ngoài.
- Sửa trạng thái của đối tượng phần tử.
- Thêm, xóa hoặc thay đổi chính nguồn đang được duyệt.
- Duyệt tuần tự và xử lý qua stream song song.

## 1. forEach nào đang được gọi?

Các biểu thức có tên gần nhau nhưng hợp đồng không hoàn toàn giống nhau:

| Biểu thức | Đối tượng nhận lời gọi | Tham số hành động | Phạm vi cần đọc |
| --- | --- | --- | --- |
| `list.forEach(action)` | Một Iterable, chẳng hạn List | `Consumer<E>` | Hợp đồng Iterable và lớp collection |
| `map.forEach(action)` | Một Map | `BiConsumer<K, V>` | Hợp đồng Map và lớp triển khai |
| `stream.forEach(action)` | Một Stream | `Consumer<T>` | Hợp đồng stream, nhất là không can thiệp nguồn |
| `stream.forEachOrdered(action)` | Một Stream | `Consumer<T>` | Thứ tự gặp phần tử và cách xử lý stream |
| `iterator.forEachRemaining(action)` | Một Iterator đã có vị trí duyệt | `Consumer<E>` | Hợp đồng iterator và phần còn lại |

Ngoài ra còn có vòng lặp ngôn ngữ:

```java
for (String name : names) {
    System.out.println(name);
}
```

Đây là vòng **for-each**, không phải lời gọi phương thức `forEach`.

Vòng for-each cho phép dùng break hoặc continue theo quy tắc vòng lặp. Lambda truyền vào forEach là một thân hàm khác, nên không thể áp dụng các từ khóa điều khiển như thể vẫn đang viết trực tiếp trong vòng lặp bên ngoài.

## 2. Lambda đóng vai trò gì trong forEach?

### 2.1. Consumer nhận một phần tử và không trả kết quả

Ví dụ minh họa trong một phương thức:

```java
names.forEach(name -> System.out.println(name));
```

Lambda nhận một tên tại mỗi lần được gọi. Nó không trả về danh sách mới.

Có thể viết bằng method reference:

```java
names.forEach(System.out::println);
```

`Consumer<T>` có phương thức chức năng `accept(T)` trả về void. Nó phù hợp các hành động có tác dụng quan sát được như in dữ liệu, gửi thông tin hoặc ghi vào một đích kết quả riêng. Xem [API Consumer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Consumer.html).

Một biểu thức gọi phương thức trả boolean, chẳng hạn `result.add(value)`, vẫn có thể dùng trong lambda phù hợp Consumer; giá trị trả về của lời gọi đó không được dùng làm kết quả của forEach.

### 2.2. Map truyền khóa và giá trị

```java
levels.forEach((name, level) ->
        System.out.println(name + "=" + level));
```

Đoạn này nhận hai đối số của mỗi ánh xạ, không phải một `Map.Entry`.

`BiConsumer<K, V>` cũng trả void. Nếu cần tính và thay giá trị của mỗi khóa, `Map.replaceAll` thể hiện ý định đó tốt hơn việc giả định lambda của forEach trả giá trị mới. Xem [API BiConsumer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/BiConsumer.html).

### 2.3. Gán lại tham số không thay phần tử trong nguồn

Trong:

```java
names.forEach(name -> {
    name = name.toUpperCase(Locale.ROOT);
});
```

biến tham số `name` nhận một giá trị mới trong lần gọi lambda đó. Nó không phải một “ô danh sách” để phép gán tự ghi ngược vào list.

Với các chuỗi, `toUpperCase` tạo hoặc trả một giá trị chuỗi phù hợp; nó không sửa chính đối tượng String cũ. Muốn tạo danh sách chữ hoa, dùng kết quả riêng hoặc phép biến đổi phù hợp. Muốn thay từng phần tử tại chỗ, dùng `List.replaceAll` trên list hỗ trợ thay thế.

Các đoạn ngắn trong phần này cần import và biến phù hợp; chương trình độc lập xuất hiện ở phần sau.

## 3. Biến được lambda sử dụng: final không có nghĩa dữ liệu bất biến

Biến cục bộ bên ngoài được lambda sử dụng phải final hoặc **effectively final**: không bị gán lại sau khi khởi tạo theo quy tắc ngôn ngữ.

Mẫu hợp lệ về cú pháp:

```java
List<String> result = new ArrayList<>();
names.forEach(name -> result.add(name));
```

`result` không bị gán sang một danh sách khác, dù nội dung đối tượng mà nó tham chiếu có thay đổi.

Mẫu không biên dịch:

```java
// Minh họa quy tắc bắt biến cục bộ, không phải chương trình để chạy.
// int count = 0;
// names.forEach(name -> count++);
```

Cấm sửa biến cục bộ được bắt không đồng nghĩa cấm mọi tác dụng phụ. Ngược lại, việc một lời gọi như `source.add(...)` biên dịch được không chứng minh nó được phép trong lượt duyệt nguồn.

Dùng một mảng một phần tử hoặc AtomicInteger chỉ để vượt hạn chế bắt biến có thể che giấu thiết kế khó hiểu. Nếu mục tiêu là đếm hoặc tính tổng, cân nhắc `count`, `sum` hoặc phép reduce phù hợp, thay vì thêm trạng thái chia sẻ khi không cần.

Quy tắc của biến cục bộ được lambda sử dụng thuộc [JLS 17, phần lambda body](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27.2).

## 4. return, break và ngoại lệ không có cùng tác dụng

### 4.1. return chỉ kết thúc lần gọi lambda hiện tại

```java
names.forEach(name -> {
    if (name.length() == 2) {
        return;
    }
    System.out.println(name);
});
```

Tên có độ dài 2 bị bỏ qua ở hành động đó. ForEach vẫn tiếp tục với phần tử sau.

Return không:

- Thoát khỏi toàn bộ phương thức đang gọi forEach.
- Dừng lượt duyệt của forEach.
- Trả một kết quả tổng hợp ra ngoài.

### 4.2. Cần dừng sớm thì chọn cấu trúc phù hợp

Nếu điều khiển luồng cần break hoặc return khỏi phương thức hiện tại, vòng lặp thường rõ hơn.

Nếu mục tiêu là kiểm tra một điều kiện, có thể dùng thao tác stream có ý nghĩa dừng sớm:

```java
boolean hasLongName =
        names.stream().anyMatch(name -> name.length() > 3);
```

Không cần duyệt toàn bộ bằng forEach rồi dùng một biến cờ ngoài để giả lập việc tìm kiếm.

Không nên cố tình ném ngoại lệ bình thường chỉ để dùng như break khi có cách điều khiển rõ ràng hơn.

### 4.3. Ngoại lệ làm gián đoạn nhưng không hoàn tác

Với `Iterable.forEach`, nếu hành động ném ngoại lệ, ngoại lệ được chuyển ra bên gọi và lượt duyệt không tiếp tục như một lần hoàn tất bình thường.

Những hành động đã thực hiện trước lỗi không tự được hoàn tác. Nếu lambda đã ghi vào danh sách kết quả hoặc gửi một yêu cầu ra ngoài, forEach không cung cấp cơ chế giao dịch để quay lại trạng thái đầu.

Consumer và BiConsumer không khai báo tùy ý checked exception trong chữ ký phương thức chức năng. Nếu hành động cần I/O có checked exception, phải quyết định xử lý, chuyển thành loại phù hợp hoặc dùng vòng lặp/phương thức có hợp đồng lỗi rõ ràng. Việc đổi sang lambda không loại bỏ trách nhiệm xử lý lỗi.

## 5. Chương trình hoàn chỉnh về lambda và luồng thực thi

Lưu vào **ForEachLambdaDemo.java**. Các API được dùng tương thích Java 17 trở lên:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

public class ForEachLambdaDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>(List.of("An", "Binh", "Chi"));

        List<String> uppercase = new ArrayList<>();
        names.forEach(name -> uppercase.add(name.toUpperCase(Locale.ROOT)));
        System.out.println("Source: " + names);
        System.out.println("Separate result: " + uppercase);

        names.forEach(name -> {
            name = name.toUpperCase(Locale.ROOT);
        });
        System.out.println("After parameter assignment: " + names);

        List<String> accepted = new ArrayList<>();
        names.forEach(name -> {
            if (name.length() == 2) {
                return;
            }
            accepted.add(name);
        });
        System.out.println("After lambda return: " + accepted);

        Map<String, Integer> levels = new LinkedHashMap<>();
        levels.put("An", 1);
        levels.put("Binh", 2);
        List<String> rows = new ArrayList<>();
        levels.forEach((name, level) -> rows.add(name + "=" + level));
        System.out.println("Map rows: " + rows);

        List<String> processed = new ArrayList<>();
        try {
            names.forEach(name -> {
                if (name.equals("Binh")) {
                    throw new IllegalArgumentException("stop");
                }
                processed.add(name);
            });
        } catch (IllegalArgumentException ex) {
            System.out.println("Failure: " + ex.getMessage());
        }
        System.out.println("Processed before failure: " + processed);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ForEachLambdaDemo.java
java ForEachLambdaDemo
```

Stdout:

```text
Source: [An, Binh, Chi]
Separate result: [AN, BINH, CHI]
After parameter assignment: [An, Binh, Chi]
After lambda return: [Binh, Chi]
Map rows: [An=1, Binh=2]
Failure: stop
Processed before failure: [An]
```

### 5.1. Tạo kết quả khác không làm đổi nguồn

Danh sách `uppercase` độc lập với `names`. Lambda chỉ thêm vào đích khác, nên nguồn vẫn là `[An, Binh, Chi]`.

Đây là trường hợp tuần tự và các danh sách không bị luồng khác truy cập trong chương trình. Không suy ra rằng cùng kiểu ghi kết quả này vẫn an toàn khi chuyển ngay sang parallelStream.

### 5.2. Gán tham số và return

Phép gán `name = ...` không thay nội dung list, đúng như dòng `After parameter assignment`.

Return bỏ qua An nhưng Binh và Chi vẫn được thêm vào `accepted`. Nó kết thúc lần xử lý tên hiện tại, không kết thúc cả forEach.

### 5.3. Map và lỗi giữa chừng

`LinkedHashMap` trong ví dụ duyệt theo thứ tự thêm ánh xạ, nên `rows` có hai chuỗi đúng thứ tự đã in.

Ở lượt cuối, An được thêm vào `processed`; đến Binh thì phát sinh lỗi trước khi thêm. Chi không được xử lý tiếp. Sau khi bắt ngoại lệ, `processed` vẫn chứa An: phần tác dụng trước lỗi không bị hoàn tác.

## 6. Thay đổi nguồn trong action: giới hạn quan trọng

Hợp đồng `Iterable.forEach` không đưa ra bảo đảm chung nếu action tạo tác dụng phụ làm thay đổi nguồn phần tử, trừ khi lớp ghi đè có quy định riêng về thay đổi đồng thời. Xem [API Iterable.forEach](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Iterable.html#forEach(java.util.function.Consumer)).

Mẫu cần tránh với ArrayList thông thường:

```java
// Minh họa thay đổi chính nguồn đang được duyệt.
numbers.forEach(number -> {
    if (number % 2 == 0) {
        numbers.remove(number);
    }
});
```

Nguồn là `numbers`; action lại xóa khỏi `numbers`. Đây không phải Iterator.remove của một iterator đang được điều khiển tường minh.

Thêm phần tử vào chính nguồn cũng có vấn đề tương tự:

```java
// Không dùng để kỳ vọng phần tử mới luôn được duyệt trong cùng lượt.
numbers.forEach(number -> numbers.add(number * 10));
```

Không đặt ra giả định rằng:

- Mọi phần tử mới chắc chắn được xử lý.
- Vòng lặp sẽ chỉ nhìn dữ liệu lúc bắt đầu.
- Luôn ném ngoại lệ ngay tại lời gọi sửa.
- Chạy xong không lỗi là bằng chứng cách dùng hợp lệ.

Với các collection thông thường, chọn một chiến lược thay đổi nguồn được nêu rõ trong hợp đồng thay vì dựa vào kết quả tình cờ của một lần chạy.

### 6.1. ConcurrentModificationException không chỉ liên quan nhiều luồng

Một luồng vừa duyệt vừa sửa nguồn có thể gây ngoại lệ này. Từ “Concurrent” ở đây không chứng minh nhất thiết có hai luồng đang chạy.

Với ArrayList, cơ chế phát hiện thay đổi ngoài lượt duyệt hỗ trợ tìm lỗi nhưng không bảo đảm phát hiện mọi hành vi sai. Không dùng việc bắt ngoại lệ như cách đồng bộ hoặc điều khiển việc xóa. Xem [API ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html).

### 6.2. Không đổi kích thước chưa chắc đã đủ

Thay một ô bằng `set`, sắp xếp lại nguồn hoặc thay đổi thứ tự cũng ảnh hưởng những gì lượt duyệt đọc. Không suy từ “không có add/remove” thành “được phép làm mọi thứ bên trong forEach”.

Nếu mục tiêu là thay từng phần tử, dùng `replaceAll` hoặc một cơ chế cập nhật có hợp đồng phù hợp. Nếu cần sắp xếp, thực hiện ở một bước riêng với điều kiện sử dụng rõ ràng.

### 6.3. Nguồn có thể bị sửa gián tiếp

Action không nhất thiết gọi đúng tên biến nguồn để gây thay đổi.

Các trường hợp cần nhận diện:

- Hai biến cùng tham chiếu một danh sách.
- Sửa một `subList` chia sẻ dữ liệu nền với list đang duyệt.
- Duyệt map nhưng sửa map qua `keySet` hoặc `values`.
- Gọi một phương thức phụ trợ hoặc callback mà bên trong sửa nguồn.
- Một luồng khác sửa nguồn trong khi action đang chạy.

Đổi tên biến không tạo ra một collection độc lập.

## 7. Sửa phần tử khác với sửa cấu trúc chứa phần tử

Có thể cần đánh dấu một đối tượng đã xử lý, tăng một bộ đếm thuộc đối tượng hoặc cập nhật trạng thái nghiệp vụ của nó.

Những việc đó không tự thêm hoặc xóa một vị trí trong list. Tuy nhiên, vẫn phải xem ảnh hưởng của thay đổi:

- Nếu phần tử cũng là phần tử của HashSet hoặc khóa của HashMap, sửa dữ liệu tham gia equals/hashCode có thể làm hỏng ý nghĩa tra cứu.
- Nếu phần tử hoặc khóa nằm trong cây có thứ tự, sửa trường quyết định thứ tự không tự tổ chức lại cây.
- Nếu nhiều phần tử tham chiếu cùng một đối tượng, một lần sửa có thể nhìn thấy ở nhiều nơi.
- Nếu xử lý song song, đối tượng phần tử có thể là trạng thái dùng chung cần phối hợp.

Vì vậy, không gộp mọi thay đổi thành một loại, cũng không mặc định mọi thao tác sửa đối tượng trong lambda đều an toàn.

Một danh sách không cho thêm/xóa cũng chưa chắc chứa các đối tượng bất biến. “Collection không cho sửa” và “toàn bộ dữ liệu bên trong không thể thay đổi” là hai bảo đảm khác nhau.

## 8. Chọn thao tác theo ý định thay đổi

| Ý định | Cách thường rõ ràng hơn |
| --- | --- |
| Chỉ thực hiện hành động với từng phần tử | `forEach` hoặc vòng lặp |
| Xóa các phần tử thỏa điều kiện | `removeIf` trên nguồn hỗ trợ |
| Vừa duyệt vừa xóa chính phần tử vừa lấy | Iterator tường minh và `Iterator.remove` nếu được hỗ trợ |
| Thay từng phần tử của list | `List.replaceAll` |
| Thay giá trị của từng khóa map | `Map.replaceAll` |
| Biến đổi/lọc để tạo dữ liệu mới | `map`, `filter`, collect/toList hoặc đích kết quả riêng tuần tự |
| Thêm vào nguồn theo dữ liệu cũ | Tích lũy riêng, thêm sau lượt duyệt |
| Duyệt bản dữ liệu theo thời điểm | Tạo bản sao cấu trúc trong điều kiện đồng thời phù hợp |

### 8.1. removeIf và replaceAll

`removeIf` nêu rõ điều kiện loại phần tử. Predicate trả boolean nhưng không nên tự sửa thêm cấu trúc nguồn đang được xử lý. Xem [API Collection.removeIf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#removeIf(java.util.function.Predicate)).

`List.replaceAll` dùng giá trị do hàm trả về để thay mỗi phần tử; đây là điều mà việc gán lại tham số trong Consumer không thực hiện. Nguồn phải hỗ trợ thay thế. Xem [API List.replaceAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#replaceAll(java.util.function.UnaryOperator)).

Các thao tác chuyên dụng vẫn có điều kiện và giới hạn riêng. Chúng không phải quyền cho lambda thực hiện thêm mọi thay đổi ngoài nhiệm vụ mà API đang điều khiển.

### 8.2. Tích lũy thay đổi rồi áp dụng sau

Nếu cần tạo phần tử mới dựa trên dữ liệu hiện tại, có thể thêm chúng vào một danh sách `additions` khác. Sau khi lượt duyệt nguồn kết thúc, mới gọi `source.addAll(additions)`.

Phần tử vừa thêm không tự được xử lý lại trong lượt cũ. Nếu nghiệp vụ yêu cầu xử lý một hàng đợi liên tục sinh tác vụ, hãy thiết kế bằng hàng đợi và điều kiện dừng phù hợp.

### 8.3. Duyệt bản sao cấu trúc

Với một chương trình tuần tự, có thể lấy `new ArrayList<>(source)`, duyệt bản sao đó rồi sửa nguồn gốc. Lượt duyệt lúc này không đi trên cùng cấu trúc bị sửa.

Giới hạn cần nhớ:

- Tạo bản sao có chi phí bộ nhớ và thời gian.
- Bản sao thường chỉ sao chép tham chiếu, không nhân bản sâu các đối tượng phần tử.
- Nếu nguồn bị sửa đồng thời ngay trong lúc sao chép, việc tạo bản sao không tự trở thành một thao tác chụp dữ liệu nguyên tử.
- Xóa theo giá trị trong nguồn có phần tử bằng nhau cần đúng ý định về lần xuất hiện.

Không dùng view hoặc một biến alias thay cho bản sao rồi kỳ vọng có sự tách rời.

## 9. Chương trình hoàn chỉnh về các cách thay đổi có chủ đích

Lưu vào **SafeTraversalChangesDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class SafeTraversalChangesDemo {
    public static void main(String[] args) {
        List<Integer> numbers =
                new ArrayList<>(List.of(1, 2, 3, 4, 5, 6));
        numbers.removeIf(number -> number % 2 == 0);
        System.out.println("After removeIf: " + numbers);

        List<String> labels = new ArrayList<>(List.of("a", "b", "c"));
        labels.replaceAll(label -> "[" + label + "]");
        System.out.println("After replaceAll: " + labels);

        List<Integer> source = new ArrayList<>(List.of(1, 2, 3));
        List<Integer> additions = new ArrayList<>();
        source.forEach(number -> {
            if (number % 2 != 0) {
                additions.add(number * 10);
            }
        });
        source.addAll(additions);
        System.out.println("After staged additions: " + source);

        List<String> tasks =
                new ArrayList<>(List.of("keep", "done", "later"));
        new ArrayList<>(tasks).forEach(task -> {
            if (task.equals("done")) {
                tasks.remove(task);
            }
        });
        System.out.println("After snapshot traversal: " + tasks);

        List<String> tokens =
                new ArrayList<>(Arrays.asList("A", null, "B", null));
        Iterator<String> iterator = tokens.iterator();
        while (iterator.hasNext()) {
            if (iterator.next() == null) {
                iterator.remove();
            }
        }
        System.out.println("After iterator removal: " + tokens);

        Map<String, Integer> stock = new LinkedHashMap<>();
        stock.put("pen", 0);
        stock.put("book", 3);
        stock.put("bag", 0);
        stock.entrySet().removeIf(entry -> entry.getValue() == 0);
        stock.replaceAll((code, quantity) -> quantity + 1);
        System.out.println("Map after explicit changes: " + stock);

        List<Integer> squares = List.of(1, 2, 3, 4)
                .parallelStream()
                .map(number -> number * number)
                .toList();
        System.out.println("Parallel collected result: " + squares);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 SafeTraversalChangesDemo.java
java SafeTraversalChangesDemo
```

Stdout:

```text
After removeIf: [1, 3, 5]
After replaceAll: [[a], [b], [c]]
After staged additions: [1, 2, 3, 10, 30]
After snapshot traversal: [keep, later]
After iterator removal: [A, B]
Map after explicit changes: {book=4}
Parallel collected result: [1, 4, 9, 16]
```

### Đọc các bước

- `removeIf` điều khiển việc xóa số chẵn, nên danh sách còn 1, 3 và 5.
- `replaceAll` thay các chuỗi bằng giá trị mới có dấu ngoặc.
- Action thêm vào `additions`, không thêm vào nguồn đang duyệt; sau đó mới áp dụng một lần.
- Lượt xử lý tasks đi trên một bản ArrayList riêng. Các giá trị chuỗi trong ví dụ không lặp nên việc xóa `"done"` theo giá trị có ý nghĩa rõ.
- Iterator tường minh xóa null qua chính `iterator.remove()`, không qua forEach.
- Map loại entry hết hàng rồi tăng các giá trị bằng thao tác dành cho mục tiêu tương ứng.
- Stream song song tạo kết quả bằng `map(...).toList()`, không dùng nhiều luồng cùng gọi add vào một ArrayList ngoài.

Chương trình dùng các collection và dữ liệu không bị luồng khác thay đổi. Các ví dụ là những chiến lược khác nhau, không phải lời khuyên ghép tất cả bước vào mọi tác vụ xử lý.

## 10. Map.forEach cũng cần giới hạn thay đổi nguồn

Mẫu xóa key của chính map bên trong `map.forEach` không phải cách viết portable cho một map thông thường.

Nếu cần loại ánh xạ theo giá trị, có thể dùng:

```java
stock.entrySet().removeIf(entry -> entry.getValue() == 0);
```

Đoạn minh họa giả định map có thể sửa, các giá trị Integer không null và view hỗ trợ xóa.

Nếu cần thay giá trị của mọi khóa:

```java
stock.replaceAll((code, quantity) -> quantity + 1);
```

Gán `quantity = quantity + 1` trong BiConsumer chỉ đổi tham số cục bộ. Lambda của replaceAll trả giá trị để API thực hiện cập nhật.

Default method của Map không tự cung cấp bảo đảm đồng bộ hay giao dịch cho cả lượt. Map cụ thể có thể có chính sách khác, nên hãy đọc đúng lớp khi dùng đồng thời. Xem [API Map.forEach](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#forEach(java.util.function.BiConsumer)) và [Map.replaceAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#replaceAll(java.util.function.BiFunction)).

## 11. Stream.forEach: thêm quy tắc không can thiệp nguồn

Stream xử lý một nguồn qua một pipeline. Các hành vi truyền vào pipeline thường cần **không can thiệp nguồn** và không phụ thuộc trạng thái thay đổi trong quá trình xử lý.

Mẫu cần tránh:

```java
// Không dùng để xóa chính nguồn của stream.
numbers.stream().forEach(number -> {
    if (number < 0) {
        numbers.remove(number);
    }
});
```

Stream tuần tự không làm việc sửa nguồn thành hợp lệ. Non-interference liên quan đến hợp đồng xử lý nguồn, không chỉ là tránh tranh chấp giữa nhiều luồng.

Nếu muốn tạo danh sách không có số âm:

```java
List<Integer> nonNegative = numbers.stream()
        .filter(number -> number >= 0)
        .toList();
```

Nếu muốn xóa ngay trên nguồn có hỗ trợ, removeIf thường mô tả đúng ý định hơn.

`Stream.toList()` trả danh sách không cho sửa; khi cần một ArrayList có thể sửa, có thể chọn collector phù hợp như `Collectors.toCollection(ArrayList::new)`. Đích kết quả là một quyết định riêng với việc giữ nguồn không bị can thiệp.

Các quy tắc về nguồn, trạng thái và tác dụng phụ được giải thích trong [tài liệu java.util.stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html).

## 12. forEach song song và trạng thái chia sẻ

Mẫu không an toàn khi dùng ArrayList thông thường làm đích chung:

```java
// Không dùng làm cách thu kết quả song song.
List<Integer> result = new ArrayList<>();
numbers.parallelStream().forEach(number ->
        result.add(number * number));
```

Các action có thể chạy trên nhiều luồng. Lambda không tự cấp khóa cho result. Có thể xảy ra mất dữ liệu, tranh chấp hoặc lỗi khác; không nên gán một stdout cố định cho đoạn dùng sai này.

Cách tạo dữ liệu mới thường rõ hơn:

```java
List<Integer> result = numbers.parallelStream()
        .map(number -> number * number)
        .toList();
```

API thu kết quả điều khiển quá trình kết hợp, thay vì để các action tùy ý sửa một ArrayList dùng chung.

### Thứ tự thực hiện khác thứ tự nguồn

`Stream.forEach` không bảo đảm thứ tự gặp phần tử khi xử lý song song. Một List có thứ tự không làm các action song song tự hoàn thành theo thứ tự đó.

Nếu cần thực hiện action theo encounter order của stream, xem `forEachOrdered`. Nó không cho phép bỏ qua giới hạn thay đổi nguồn, không biến mọi dữ liệu bên ngoài thành an toàn trước các hoạt động khác, và có thể ảnh hưởng khả năng chạy song song.

Không đoán thứ tự từ một lần quan sát output. Xem [Stream.forEach](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#forEach(java.util.function.Consumer)) và [Stream.forEachOrdered](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#forEachOrdered(java.util.function.Consumer)).

## 13. Lớp concurrent có chính sách riêng, không phải ngoại lệ tùy ý

Một số cấu trúc được thiết kế để hỗ trợ thay đổi trong khi duyệt. Chúng có thể dùng ảnh chụp hoặc cơ chế duyệt phản ánh thay đổi theo những bảo đảm riêng.

Chẳng hạn:

- Iterator của CopyOnWriteArrayList làm việc với ảnh chụp, không phản ánh các thay đổi sau khi tạo iterator.
- ConcurrentHashMap cung cấp các thao tác duyệt phù hợp môi trường đồng thời, nhưng một lượt duyệt không mặc định là ảnh chụp nguyên tử của toàn bộ map.

Những đặc điểm này phải lấy từ hợp đồng lớp và phương thức thực tế. Không suy từ “thread-safe” thành “action nào sửa dữ liệu cũng đúng nghiệp vụ”, hoặc từ một iterator snapshot thành bảo đảm cho mọi API tương tự.

Ngay cả khi collection cho phép thay đổi đồng thời, action vẫn phải an toàn với trạng thái bên ngoài mà nó sửa. Các thay đổi hợp lệ có thể không được nhìn thấy đầy đủ trong lượt đang chạy, tùy chính sách.

Xem [CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html) và [ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html).

### Iterator.forEachRemaining không cấp quyền remove trong action

Không dùng sự tồn tại của một biến iterator để kết luận rằng có thể gọi remove tùy ý trong lambda của forEachRemaining.

Hợp đồng chung không bảo đảm hành vi nếu action sửa nguồn, kể cả gọi remove, trừ chính sách riêng được công bố. Cũng không có bảo đảm chung cho remove sau khi gọi forEachRemaining.

Khi cần xóa phần tử vừa đọc bằng iterator, vòng while với next và remove tường minh thể hiện đúng cơ chế. Xem [API Iterator.forEachRemaining](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html#forEachRemaining(java.util.function.Consumer)).

## 14. Chẩn đoán và tự rà soát

Trước một lời gọi forEach, hỏi:

1. Đây là Iterable.forEach, Map.forEach, Stream.forEach hay Iterator.forEachRemaining?
2. Action chỉ quan sát, sửa phần tử, sửa nguồn hay ghi sang một cấu trúc khác?
3. Cấu trúc “khác” có thật sự độc lập, hay là alias/view của nguồn?
4. Có cần dừng sớm hoặc trả kết quả ra ngoài không?
5. Có đang nhầm gán tham số với cập nhật phần tử/ánh xạ không?
6. Nếu một action lỗi giữa chừng, các tác dụng trước đó có chấp nhận được không?
7. Nếu chuyển sang song song, trạng thái bên ngoài nào trở thành dùng chung?
8. Thứ tự được yêu cầu là thứ tự dữ liệu hay thứ tự hoàn thành action?
9. Lớp collection cụ thể công bố chính sách thay đổi đồng thời nào?
10. Một thao tác chuyên dụng như removeIf, replaceAll, map/filter hoặc vòng lặp có làm ý định rõ hơn không?

## 15. Bài tập tự kiểm tra

1. Trong chương trình đầu, vì sao `name = ...` không đổi nguồn nhưng `uppercase.add(...)` lại đổi được danh sách kết quả?
2. Nếu return xuất hiện ở phần tử đầu tiên, những phần tử sau có còn được xử lý không?
3. Vì sao có thể nhận ConcurrentModificationException dù chương trình chỉ có một luồng?
4. Đổi đoạn xóa số âm trong forEach thành removeIf và thành cách tạo một kết quả mới; so sánh tác động lên nguồn.
5. Với danh sách chứa cùng một đối tượng ở hai vị trí, một bản sao ArrayList có làm dữ liệu đối tượng tách rời không?
6. Giải thích vì sao đổi `stream()` thành `parallelStream()` có thể làm một đích kết quả ArrayList trước đó dùng được trở nên không an toàn.
7. Nêu cách bảo toàn ý định “xử lý theo thứ tự ưu tiên” mà không dựa vào thứ tự output tình cờ.

ForEach hữu ích khi hành động trên từng phần tử đã rõ. Khi hành động bắt đầu quyết định cấu trúc nguồn, điều khiển dừng sớm hoặc kết hợp trạng thái giữa nhiều lần gọi, hãy chọn đúng API và cơ chế phối hợp cho yêu cầu đó.
