# Boxing, cấp phát đối tượng, thu gom rác và tính cục bộ bộ nhớ

## 1. Từ thao tác trên collection đến chi phí phần cứng

Hai cách lưu và duyệt cùng một tập số có thể cùng có độ phức tạp O(n) nhưng khác đáng kể về thời gian, lượng cấp phát và bộ nhớ đang giữ. Big O mô tả cách số thao tác tăng theo quy mô; nó không mô tả đầy đủ chi phí chuyển kiểu, số đối tượng, các lần lần theo tham chiếu hay thời gian chờ dữ liệu từ bộ nhớ.

Trong bài này, bốn khái niệm nối với nhau:

- **Đóng hộp (boxing)**: chuyển giá trị nguyên thủy, chẳng hạn `int`, sang đối tượng kiểu bọc như `Integer`.
- **Cấp phát (allocation)**: dành bộ nhớ cho đối tượng hoặc mảng thực sự xuất hiện khi chương trình chạy.
- **Thu gom rác (garbage collection, GC)**: xác định và thu hồi bộ nhớ của đối tượng không còn cần giữ sống theo quy tắc của JVM.
- **Tính cục bộ bộ nhớ (memory locality)**: mức độ các truy cập tiếp theo có thể tận dụng dữ liệu đã ở gần hoặc đã nằm trong bộ nhớ đệm của CPU.

Chuỗi nguyên nhân có thể là:

```text
Chọn biểu diễn dữ liệu và kiểu collection
    -> cần giá trị nguyên thủy hay tham chiếu tới đối tượng?
    -> có boxing, nút, mảng thay thế hoặc đối tượng tạm?
    -> lượng cấp phát, lượng dữ liệu sống và đồ thị tham chiếu thay đổi
    -> công việc GC và đường truy cập bộ nhớ thay đổi
    -> thông lượng, độ trễ và dung lượng bộ nhớ có thể thay đổi
```

Đây là đường phân tích để đặt giả thuyết và đo, không phải công thức khẳng định mọi collection có boxing đều chậm trong mọi tình huống.

## 2. Boxing và unboxing xuất hiện ở đâu?

### 2.1. Collection tổng quát giữ kiểu tham chiếu

Với Java 17/21, tham số kiểu của generic phải là kiểu tham chiếu. `List<Integer>` hợp lệ, còn `List<int>` không hợp lệ. Vì thế một danh sách số nguyên tiêu chuẩn thường giữ tham chiếu tới `Integer`, trong khi `int[]` chứa trực tiếp các giá trị nguyên thủy.

Đoạn sau minh họa phép chuyển đổi; cần đặt trong một phương thức có import phù hợp:

```java
List<Integer> values = new ArrayList<>();
int input = 1_000_000;
values.add(input);        // int -> Integer: boxing
int output = values.get(0); // Integer -> int: unboxing
```

Có thể hiểu các phép chuyển đổi này tương ứng với việc lấy đối tượng kiểu bọc và đọc lại giá trị nguyên thủy, thường thấy dưới dạng `Integer.valueOf(input)` và `intValue()` trong mã biên dịch. Cách diễn đạt đó không phải lời hứa về số đối tượng vật lý sau khi JIT tối ưu.

Vòng lặp `for (int value : values)` cũng unbox từng phần tử được lấy ra. Phép toán số học với biến kiểu bọc có thể unbox trước khi tính, rồi boxing trở lại nếu kết quả gán cho kiểu bọc. Các quy tắc chuyển đổi được nêu trong [JLS §5.1.7–§5.1.8](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.7).

### 2.2. Bộ đệm đối tượng kiểu bọc không phải bộ nhớ đệm CPU

`Integer.valueOf(int)` dùng lại đối tượng cho ít nhất miền từ `-128` đến `127`, và có thể dùng lại cho giá trị ngoài miền đó. Do đó boxing không luôn tạo đối tượng mới. [Tài liệu `Integer.valueOf`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Integer.html#valueOf(int)).

Cần phân biệt hai từ “cache”:

| Cơ chế | Cái được dùng lại | Tác động chính |
| --- | --- | --- |
| Bộ đệm đối tượng `Integer` | Một số đối tượng kiểu bọc | Có thể tránh cấp phát đối tượng kiểu bọc mới |
| Bộ nhớ đệm CPU | Các khối dữ liệu được phần cứng nạp gần CPU | Có thể giảm thời gian chờ khi truy cập dữ liệu |

Dùng lại một `Integer` không bảo đảm mọi truy cập đều trúng bộ nhớ đệm CPU. Ngược lại, một đối tượng mới vẫn có thể được truy cập thuận lợi trong một giai đoạn nhất định.

Không dùng `==` giữa hai biến `Integer` để kiểm tra giá trị số. Nó so danh tính tham chiếu và có thể tình cờ cho kết quả mong muốn nhờ bộ đệm. Dùng `equals`, `Objects.equals` khi có thể có `null`, hoặc chuyển về nguyên thủy sau khi xử lý `null` theo yêu cầu nghiệp vụ. Không dựa vào một giá trị lớn để khẳng định rằng hai lần boxing chắc chắn cho tham chiếu khác nhau.

### 2.3. `null` và ngữ nghĩa phải được giải quyết trước tối ưu

Collection kiểu bọc có thể cho phép `null`; một giá trị `int` không biểu diễn được `null`. Unbox một tham chiếu `null` ném `NullPointerException`.

Khi chuyển từ `List<Integer>` sang `int[]` hoặc một cấu trúc chuyên cho nguyên thủy, phải quyết định cách biểu diễn dữ liệu thiếu. Không tùy tiện đổi `null` thành `0` nếu `0` là dữ liệu hợp lệ. Giảm cấp phát không được làm thay đổi kết quả chương trình.

## 3. Cấp phát không chỉ đến từ boxing

Một thao tác trên collection có thể liên quan nhiều lớp đối tượng:

| Nguồn cấp phát có thể có | Ví dụ | Điều cần phân biệt |
| --- | --- | --- |
| Đối tượng kiểu bọc | Đưa giá trị số vào collection tham chiếu | Bộ đệm hoặc tối ưu có thể tránh một số cấp phát |
| Nút cấu trúc | Thêm phần tử vào danh sách liên kết hoặc ánh xạ vào bảng băm | Nút và đối tượng dữ liệu là hai đối tượng khác nhau |
| Mảng lưu trữ mới | Mở rộng danh sách mảng | Mảng mới không đồng nghĩa sao chép sâu các phần tử |
| Collection trung gian | Tạo một danh sách kết quả ở mỗi bước xử lý | Các danh sách có thể cùng tham chiếu dữ liệu cũ |
| Đối tượng hỗ trợ | Iterator, đối tượng của pipeline hoặc lambda trong một số trường hợp | Không được mặc định mỗi lần gọi luôn tạo một đối tượng vật lý |

Ví dụ, đặt trước sức chứa `ArrayList` có thể giảm số mảng thay thế nhưng không tự loại bỏ boxing ở `add(intValue)`. Tương tự, đổi `LinkedList<Integer>` sang `ArrayList<Integer>` có thể giảm các nút nhưng vẫn còn các tham chiếu và đối tượng `Integer`.

### 3.1. Đếm thao tác trong mã khác đếm đối tượng thực sự

JVM có thể tối ưu một số đối tượng không thoát ra ngoài phạm vi tính toán, chẳng hạn bằng phân tích thoát (escape analysis) và thay thế bằng các giá trị thành phần. Các khả năng đó phụ thuộc JVM, đường thực thi và quyết định biên dịch; không phải mọi đối tượng tạm đều được loại bỏ. [Tài liệu tối ưu HotSpot](https://docs.oracle.com/en/java/javase/21/vm/java-hotspot-virtual-machine-performance-enhancements.html).

Vì vậy cả hai kết luận sau đều thiếu căn cứ:

- “Mã có 10.000 phép boxing nên chắc chắn cấp phát đúng 10.000 đối tượng.”
- “JIT có escape analysis nên mọi boxing trong vòng lặp đều miễn phí.”

Đối tượng được lưu trong collection trả về hoặc được giữ để sử dụng về sau có ràng buộc khác đối tượng chỉ phục vụ một phép tính cục bộ. Cần đo lượng cấp phát của chính trường hợp đó, trong điều kiện biên dịch đại diện.

### 3.2. Một bộ cộng dồn kiểu bọc dễ tạo công việc thừa

Đoạn minh họa:

```java
Long total = 0L;
for (int value : primitiveValues) {
    total += value;
}
```

Về ngữ nghĩa, mỗi vòng phải đọc giá trị `long` từ `total`, cộng rồi chuyển kết quả về `Long`. Nếu không cần khả năng biểu diễn `null` hoặc một API đòi kiểu bọc, dùng `long total = 0L` làm rõ ý định và tránh yêu cầu boxing lặp lại ở cấp mã nguồn. Khi phải trả `Long`, có thể boxing ở ranh giới trả kết quả thay vì dùng kiểu bọc cho toàn bộ quá trình cộng.

Số đối tượng thực tế vẫn phải kiểm chứng; ví dụ này giải thích nguồn công việc có thể tránh, không đưa ra số byte hoặc số lần GC cố định.

## 4. Từ cấp phát đến công việc thu gom rác

### 4.1. Cấp phát nhiều và giữ nhiều là hai vấn đề khác nhau

Cần tách ba chỉ số:

1. **Lượng cấp phát trên một đơn vị công việc**: chẳng hạn byte cho mỗi yêu cầu hoặc mỗi lần chạy toàn bộ một batch.
2. **Tốc độ cấp phát**: byte mỗi giây.
3. **Tập dữ liệu sống**: các đối tượng còn phải giữ sống tại thời điểm đang xét.

Một dịch vụ có thể tạo rất nhiều đối tượng ngắn hạn nhưng chỉ giữ một tập dữ liệu nhỏ. Dịch vụ khác cấp phát ít mỗi giây nhưng giữ một map lớn trong nhiều giờ. Chỉ nhìn mức heap đang dùng tại một thời điểm không mô tả đầy đủ hai tải này.

Ví dụ số học giả định: mỗi yêu cầu cấp phát 2.000 byte và xử lý 10.000 yêu cầu/giây thì tốc độ cấp phát là 20.000.000 byte/giây. Đây là kết quả nhân của hai số liệu, không phải dự đoán chu kỳ GC. Sau tối ưu, nếu tốc độ cấp phát mỗi giây giảm vì chương trình xử lý ít yêu cầu hơn thì chưa thể kết luận tốt hơn; hãy xem cả byte/yêu cầu lẫn thông lượng và độ trễ.

### 4.2. Vì sao đối tượng ngắn hạn vẫn có chi phí?

Cấp phát đối tượng nhỏ có thể được JVM thực hiện rất nhanh. Tuy nhiên hệ thống vẫn cần bộ nhớ cho chúng; lượng cấp phát cao làm tăng nhu cầu thu hồi hoặc tái sử dụng vùng nhớ. Công việc GC còn phụ thuộc số đối tượng sống, các tham chiếu phải theo dõi, kiểu bộ gom rác và cấu hình heap.

Với G1 trên JDK 21, phần lớn cấp phát thông thường đi vào vùng thế hệ trẻ, còn đối tượng rất lớn có cách xử lý riêng. Thu hồi có thể phải sao chép các đối tượng còn sống. Cơ chế này giúp giải thích vì sao thời gian sống cũng quan trọng; không được áp quy trình của G1 cho mọi collector. [Tài liệu G1](https://docs.oracle.com/en/java/javase/21/gctuning/garbage-first-g1-garbage-collector1.html).

Không suy rằng thêm một đối tượng sẽ kích hoạt ngay một lần GC, cũng không suy rằng giảm một nửa số đối tượng luôn giảm một nửa thời gian tạm dừng. Quan hệ còn phụ thuộc trạng thái heap, kích thước, thời gian sống và các hoạt động đồng thời.

### 4.3. Collection có thể kéo dài thời gian sống ngoài dự kiến

Một danh sách tạm sau khi xử lý xong sẽ ít gây vấn đề hơn một cache không giới hạn tiếp tục giữ mọi kết quả. Khi đối tượng vẫn được một collection còn sống tham chiếu mạnh, GC không thể tự quyết rằng dữ liệu đó “đã cũ nên bỏ”.

Ví dụ cần kiểm tra trong ứng dụng:

- Map dùng làm cache không có giới hạn kích thước hoặc chính sách loại bỏ.
- Danh sách gắn với phiên làm việc nhưng giữ dữ liệu của nhiều yêu cầu cũ.
- Hàng đợi có tốc độ đưa vào lâu dài lớn hơn tốc độ xử lý.
- Collection được giữ trong trường `static` hoặc đối tượng sống lâu ngoài ý định.

Xử lý đúng thời gian sống và giới hạn dữ liệu thường có ý nghĩa trực tiếp hơn việc tìm cách làm GC thu hồi thứ vẫn còn được tham chiếu. `System.gc()` chỉ là đề nghị JVM nỗ lực thu hồi, không có bảo đảm về dung lượng hoặc thời điểm thu hồi cụ thể. [Tài liệu `System.gc`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#gc()).

## 5. Tính cục bộ: CPU cần đi qua những đâu để lấy một số?

### 5.1. `int[]`, `ArrayList<Integer>` và danh sách liên kết

Sơ đồ sau minh họa các tầng truy cập; vị trí thật do JVM quản lý:

```text
int[]
  [1000][1001][1002][1003]          các giá trị nằm trong mảng

ArrayList<Integer>
  [ref0][ref1][ref2][ref3]          các tham chiếu nằm trong mảng
     |     |     |     |
     v     v     v     v
  Integer Integer Integer Integer  các đối tượng nằm ngoài mảng

LinkedList<Integer>
  node0 -> node1 -> node2 -> node3  phải lần theo liên kết nút
    |        |        |        |
    v        v        v        v
  Integer  Integer  Integer  Integer
```

Duyệt tuần tự `int[]` đọc trực tiếp các giá trị được bố trí liên tiếp trong mảng. Duyệt danh sách mảng chứa số kiểu bọc phải đọc tham chiếu rồi đọc giá trị trong đối tượng được trỏ tới. Với danh sách liên kết còn có tầng nút và phụ thuộc vào liên kết tới nút tiếp theo.

Các ô của mảng tham chiếu liên tiếp không có nghĩa các đối tượng được tham chiếu cũng liên tiếp. Đối tượng có thể được cấp phát hoặc di chuyển qua các giai đoạn khác nhau. Không suy thứ tự địa chỉ vật lý chỉ từ thứ tự phần tử.

### 5.2. Bộ nhớ đệm CPU và truy cập liên tiếp

CPU thường nạp dữ liệu theo các khối của bộ nhớ đệm. Duyệt dữ liệu gần nhau có thể dùng được nhiều giá trị từ dữ liệu đã nạp và giúp cơ chế nạp trước dự đoán truy cập tiếp theo. Lần theo nhiều tham chiếu tới các vị trí phân tán có thể làm CPU phải chờ nhiều hơn, đặc biệt khi dữ liệu lớn vượt khả năng chứa của các mức bộ nhớ đệm.

Đây là cơ sở cho giả thuyết rằng biểu diễn đặc hơn có thể cải thiện việc duyệt dữ liệu. Kết quả vẫn phụ thuộc kích thước tập dữ liệu, thứ tự truy cập, phần cứng và lượng tính toán thực hiện trên mỗi phần tử.

Ví dụ chính thức của JMH so sánh mảng nguyên thủy, danh sách số kiểu bọc và danh sách bị xáo thứ tự tham chiếu để làm rõ ảnh hưởng của cách truy cập bộ nhớ. Không dùng lại các con số thời gian trong ví dụ như định luật cho máy khác. [JMH: Memory Access](https://raw.githubusercontent.com/openjdk/jmh/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_39_MemoryAccess.java).

### 5.3. Đừng quy lỗi thuật toán cho bộ nhớ đệm

Nếu duyệt `LinkedList` bằng `get(i)` cho mọi chỉ số, mỗi lần có thể phải tìm nút. Toàn bộ vòng lặp có thể thành O(n²), thay vì O(n) khi dùng iterator. Chênh lệch lớn trong phép đo như vậy có thể đến từ thuật toán truy cập trước khi cần xét đến tính cục bộ.

Thứ tự phân tích hợp lý là kiểm tra thuật toán và số thao tác, sau đó kiểm tra biểu diễn dữ liệu, lượng cấp phát và đường truy cập bộ nhớ. Big O và tính cục bộ bổ sung cho nhau; không thay thế nhau.

## 6. Chương trình Java 17+ kiểm chứng ngữ nghĩa

Lưu thành `BoxingDemo.java`. Chương trình độc lập, không có thư viện ngoài:

```java
import java.util.ArrayList;
import java.util.List;

public class BoxingDemo {
    public static void main(String[] args) {
        Integer first = 42;
        Integer second = 42;
        System.out.println("cached identity=" + (first == second));

        Integer largeA = Integer.valueOf(1_000_000);
        Integer largeB = Integer.valueOf(1_000_000);
        System.out.println("same numeric value=" + largeA.equals(largeB));

        int[] primitive = new int[5];
        List<Integer> boxed = new ArrayList<>(primitive.length);
        for (int i = 0; i < primitive.length; i++) {
            primitive[i] = 1_000_000 + i;
            boxed.add(primitive[i]);
        }

        long primitiveSum = 0;
        for (int value : primitive) {
            primitiveSum += value;
        }

        long boxedSum = 0;
        for (int value : boxed) {
            boxedSum += value;
        }

        Long boxedAccumulator = 0L;
        for (int value : primitive) {
            boxedAccumulator += value;
        }

        long streamSum = boxed.stream()
                .mapToLong(Integer::longValue)
                .sum();

        System.out.println("primitive sum=" + primitiveSum);
        System.out.println("boxed sum=" + boxedSum);
        System.out.println("boxed accumulator=" + boxedAccumulator);
        System.out.println("primitive stream sum=" + streamSum);

        boxed.add(null);
        try {
            int missing = boxed.get(boxed.size() - 1);
            System.out.println(missing);
        } catch (NullPointerException ex) {
            System.out.println("unboxing null=NullPointerException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 BoxingDemo.java
java BoxingDemo
```

Stdout chính xác:

```text
cached identity=true
same numeric value=true
primitive sum=5000010
boxed sum=5000010
boxed accumulator=5000010
primitive stream sum=5000010
unboxing null=NullPointerException
```

Cách đọc kết quả:

- Hai phép boxing hằng `42` thể hiện trường hợp dùng chung đối tượng trong miền nhỏ được bảo đảm. Điều này không biến `==` thành phép so giá trị cho kiểu bọc nói chung.
- Giá trị lớn được kiểm tra bằng `equals`; chương trình không khẳng định hai tham chiếu phải khác nhau.
- Mảng nguyên thủy và danh sách kiểu bọc cho cùng tổng; đây là bằng chứng về kết quả, không phải bằng chứng về tốc độ ngang nhau.
- `Long boxedAccumulator` cho đúng tổng nhưng có yêu cầu unboxing/boxing trong phép gán cộng. Stdout không cho biết JIT loại bỏ bao nhiêu cấp phát.
- `mapToLong` dùng luồng giá trị `long` cho bước tính tổng, nhưng danh sách nguồn vẫn chứa `Integer` và phải đọc giá trị từ chúng.
- Chỉ sau khi tính các tổng, chương trình mới thêm `null`. Việc unbox phần tử đó gây `NullPointerException` và được bắt để in thông báo ổn định.

Chương trình không đo thời gian, số đối tượng hay GC. Không thêm một vòng `nanoTime()` vào nó rồi dùng vài lần chạy làm kết luận hiệu năng.

## 7. Tránh boxing không cần thiết trong đường xử lý

### 7.1. Giữ giá trị nguyên thủy trong phần tính toán

Dùng `int`, `long`, `double` cho biến tính toán khi ngữ nghĩa cho phép. Chỉ boxing ở ranh giới cần đối tượng, chẳng hạn đưa kết quả vào API generic. Với phép tổng lớn, còn cần chọn kiểu đủ miền giá trị; tránh boxing không giải quyết lỗi tràn số.

Nếu dữ liệu vốn đã ở `List<Integer>`, việc unbox trong phép tổng là cần thiết để tính số học. Tối ưu đáng cân nhắc là tránh tạo thêm một collection kiểu bọc chỉ để chứa các kết quả trung gian rồi lại unbox chúng.

### 7.2. Dùng luồng nguyên thủy khi phù hợp

Ví dụ minh họa trong một phương thức có sẵn `List<Integer> values` không chứa `null`:

```java
long total = values.stream()
        .mapToLong(Integer::longValue)
        .sum();
```

`Stream<Integer>` là luồng tham chiếu; `IntStream`, `LongStream` và `DoubleStream` là các dạng chuyên cho nguyên thủy. Chuyển sang dạng nguyên thủy cho các phép toán tiếp theo có thể tránh boxing kết quả ở từng bước. Tuy nhiên pipeline vẫn có cơ chế hỗ trợ riêng; không mô tả nó là “không tạo bất kỳ đối tượng nào”. [Tài liệu `java.util.stream`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/package-summary.html).

Gọi `.boxed()` lại đưa giá trị về luồng kiểu bọc. Nếu cuối cùng thu thập vào `List<Integer>`, yêu cầu biểu diễn bằng đối tượng ở kết quả vẫn còn. `mapToInt` không xóa các đối tượng `Integer` đã tồn tại trong collection nguồn.

### 7.3. Đổi cấu trúc khi yêu cầu sử dụng cho phép

Mảng nguyên thủy phù hợp cho nhiều bài toán số với quy mô đã biết hoặc được quản lý rõ. Collection chuyên cho nguyên thủy của thư viện ngoài có thể cung cấp thêm thao tác nhưng phải xem hợp đồng API, cách biểu diễn phần tử thiếu và đo trong dự án cụ thể.

Không thay một map tra cứu nhanh bằng quét mảng chỉ để giảm đối tượng mà bỏ qua số lần tra cứu. Cũng không ép mọi dữ liệu nghiệp vụ thành mảng chỉ vì mảng đặc hơn. Cấu trúc cần đáp ứng kiểu truy cập, cập nhật và tính đúng trước, rồi mới tối ưu phần chi phí đã đo được.

## 8. Thiết kế phép đo để không kết luận nhầm

### 8.1. Tách các câu hỏi khác nhau

| Phép đo | Phần đặt trong thao tác được đo | Câu hỏi được trả lời |
| --- | --- | --- |
| Xây collection | Cấp phát collection, thêm dữ liệu, trả kết quả để được sử dụng | Chi phí tạo và vật chất hóa biểu diễn là bao nhiêu? |
| Duyệt collection có sẵn | Chỉ duyệt/tính; dữ liệu chuẩn bị ngoài phần đo | Chi phí đọc cấu trúc và tính toán là bao nhiêu? |
| Xử lý một yêu cầu hoặc batch hoàn chỉnh | Toàn bộ đường xử lý đại diện | Tối ưu có cải thiện mục tiêu thực tế không? |

Nếu tạo collection trong một phương án nhưng chuẩn bị sẵn cho phương án khác, kết quả không cô lập được chi phí duyệt. Ngược lại, chỉ đo duyệt không cho biết tổng chi phí tạo rồi hủy collection ở mỗi yêu cầu.

Muốn cô lập phần cấu trúc giữa hai collection tham chiếu, có thể dùng cùng các đối tượng dữ liệu làm đầu vào. Nếu mỗi phương án boxing riêng một bộ dữ liệu, phép so sánh còn chứa khác biệt về các đối tượng kiểu bọc và cách chúng được bố trí. Cần ghi rõ đang cố tình đo trường hợp nào.

### 8.2. Kiểm soát các bẫy của microbenchmark

Dùng JMH cho phép đo vi mô nghiêm túc và thiết lập dữ liệu phù hợp. Các điểm cần kiểm tra:

- Có giai đoạn làm nóng và nhiều lần đo; tách các tiến trình chạy thử độc lập khi cần đánh giá độ ổn định.
- Kết quả được trả về hoặc được tiêu thụ đúng cách để tránh trình biên dịch bỏ phép tính không có tác dụng.
- Không in stdout trong phần đang đo.
- Dùng dữ liệu đại diện: miền số nhỏ được dùng lại trong bộ đệm và miền số lớn có thể cho lượng cấp phát khác nhau.
- Thử nhiều kích thước, gồm trường hợp lớn hơn khả năng chứa của bộ nhớ đệm; không suy tuyến tính từ một danh sách rất nhỏ.
- Giữ điều kiện JDK, JVM, heap, collector và máy đo nhất quán; ghi rõ cấu hình đã dùng.

JMH có ví dụ cụ thể về việc kết quả bị loại bỏ khi mã không được sử dụng. [JMH: Dead Code](https://raw.githubusercontent.com/openjdk/jmh/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_08_DeadCode.java).

### 8.3. Đọc nhiều chỉ số thay vì chỉ thời gian trung bình

Với JMH, GC profiler có thể cung cấp tốc độ cấp phát và số byte chuẩn hóa cho mỗi thao tác. `B/op` phải được hiểu theo định nghĩa “một thao tác” trong benchmark: nếu một lần benchmark xử lý 10.000 phần tử thì đó là byte cho cả lần xử lý, trừ khi đã cấu hình cách chuẩn hóa khác.

So `gc.alloc.rate.norm` với thời gian và thông lượng; không lấy tốc độ MB/giây thấp hơn làm bằng chứng độc lập rằng mỗi yêu cầu cấp phát ít hơn. Các kết quả GC cũng cần đủ thời gian và số lần lặp để có ý nghĩa. [JMH: Profilers](https://raw.githubusercontent.com/openjdk/jmh/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_35_Profilers.java).

Ở ứng dụng thật, theo dõi đồng thời thông lượng, các phân vị độ trễ, lượng cấp phát và GC theo tải đại diện. Nếu nghi ngờ dữ liệu bị giữ quá lâu, phân tích heap và các đường tham chiếu; nếu nghi ngờ truy cập bộ nhớ, dùng profiler/phân tích phần cứng thích hợp thay vì suy ra cache miss chỉ từ thời gian chạy.

## 9. Những kết luận dễ sai và cách sửa

| Kết luận vội | Cách phân tích chính xác hơn |
| --- | --- |
| “Boxing lần nào cũng tạo đối tượng mới.” | Xét bộ đệm kiểu bọc, chia sẻ tham chiếu và tối ưu JIT; đo cấp phát thực tế |
| “GC sẽ tự xử lý nên số đối tượng không quan trọng.” | GC có chi phí và phụ thuộc dữ liệu sống; đo theo mục tiêu thông lượng/độ trễ |
| “Ít GC hơn chắc chắn nhanh hơn.” | Có thể chương trình chỉ chạy ít công việc hơn hoặc giữ dữ liệu lâu hơn; so cùng đơn vị công việc |
| “`ArrayList<Integer>` chứa các số liền nhau.” | Nó chứa các tham chiếu liền nhau trong mảng; các đối tượng `Integer` ở ngoài mảng |
| “Cùng O(n) thì duyệt gần như ngang nhau.” | Đường truy cập, boxing, số đối tượng và chi phí tính toán mỗi phần tử có thể khác |
| “Đổi sang primitive stream là xóa mọi boxing đã có.” | Dữ liệu nguồn kiểu bọc vẫn tồn tại; lợi ích nằm ở những bước được chuyển sang nguyên thủy |
| “Tạo pool cho mọi đối tượng nhỏ sẽ giảm chi phí.” | Pool có thể kéo dài thời gian sống, giữ bộ nhớ và thêm quản lý/đồng bộ; cần đo lợi ích ròng |

## 10. Thực hành phân tích một đường xử lý số

Giả sử mỗi yêu cầu nhận 100.000 số, tạo `List<Integer>`, tạo thêm danh sách kết quả sau biến đổi, tính tổng rồi bỏ các danh sách. Hãy tiến hành theo thứ tự:

1. Xác nhận đầu ra, miền giá trị, dữ liệu thiếu và khả năng tràn số.
2. Vẽ nơi bắt đầu boxing, nơi có collection trung gian và nơi unboxing để tính tổng.
3. Đo byte/yêu cầu, thông lượng và độ trễ của phiên bản hiện tại; ghi thời gian sống của kết quả.
4. Thử tính trực tiếp hoặc dùng luồng nguyên thủy để tránh vật chất hóa danh sách trung gian nếu nó không cần được dùng lại.
5. Chỉ thay biểu diễn đầu vào khi hợp đồng sử dụng cho phép; so kết quả và đo lại cùng tải.
6. Nếu lượng cấp phát đã giảm nhưng độ trễ không cải thiện, kiểm tra lại nút thắt như I/O, tính toán hoặc truy cập dữ liệu thay vì mặc định GC là nguyên nhân duy nhất.

Câu hỏi tự kiểm tra:

- Vì sao benchmark chỉ dùng các số từ `0` đến `100` có thể không đại diện cho dữ liệu số tùy ý?
- Vì sao tổng trên `List<Integer>` vẫn cần unboxing dù các đối tượng `Integer` đã tồn tại từ trước?
- Nếu đổi kiểu bộ cộng dồn từ `Long` sang `long`, điều gì được đơn giản hóa ở ngữ nghĩa và điều gì vẫn cần đo?
- Khi GC không thu hồi được một map chứa dữ liệu cũ, nên tìm tham chiếu giữ sống ở đâu?
- Vì sao xáo thứ tự tham chiếu trong danh sách có thể đổi hiệu năng dù số phần tử và số phép cộng vẫn giữ nguyên?

Một lời giải tốt phải nối được biểu diễn dữ liệu với cấp phát, thời gian sống và đường truy cập bộ nhớ, rồi chỉ ra phép đo nào xác nhận từng giả thuyết.
