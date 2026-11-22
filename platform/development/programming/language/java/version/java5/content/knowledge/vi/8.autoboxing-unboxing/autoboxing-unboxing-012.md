# Chi phí cấp phát và unboxing trong vòng lặp

## 1. Chi phí nằm ở những phép chuyển nào?

Autoboxing làm cú pháp sử dụng số trong API đối tượng ngắn hơn, nhưng một vòng lặp vẫn có thể phải đi qua các bước chuyển giữa giá trị nguyên thủy và wrapper. Khi số lượt lặp lớn, cần phân biệt chi phí tính toán, lấy dữ liệu, mở hộp và giữ các đối tượng wrapper.

Ví dụ:

```java
Long total = 0L;
for (Integer value : values) {
    total += value;
}
```

`values` ở đây là `List<Integer>`. Mỗi phép cập nhật có các bước ý nghĩa: mở hộp `total`, mở hộp `value`, cộng theo kiểu số phù hợp, boxing kết quả và lưu lại biến `total`.

Vì `Long` bất biến, câu lệnh không sửa giá trị bên trong đối tượng `Long` cũ. Nó cập nhật biến tham chiếu tới biểu diễn wrapper của kết quả.

Tuy nhiên, không được kết luận ngay rằng “mỗi lượt chắc chắn cấp phát một đối tượng trên heap”. Số phép chuyển thấy ở mã nguồn, cách biên dịch bytecode và lượng cấp phát vật lý sau tối ưu JVM là ba lớp cần được kiểm tra riêng.

Bài này dùng cú pháp Java hiện hành, chạy ví dụ bằng JDK 17 trở lên và không giả định một tốc độ cố định cho boxing trên mọi JVM.

## 2. Dùng bộ tích lũy nguyên thủy để tránh boxing kết quả lặp lại

Đổi bộ tích lũy thành `long`:

```java
long total = 0L;
for (int value : values) {
    total += value;
}
```

Vòng lặp này vẫn đọc từ `List<Integer>`, nên mỗi phần tử cần được dùng như `int` qua unboxing. Nhưng `total` đã là `long`; kết quả mỗi phép cộng được giữ ở dạng nguyên thủy, không cần boxing lại tổng chỉ để tiếp tục cộng.

So sánh về mặt thao tác ngôn ngữ:

| Cách tổ chức | Mở hộp phần tử đầu vào | Boxing lại bộ tích lũy trong thân vòng lặp |
| --- | --- | --- |
| `Long total` và nguồn `List<Integer>` | Có | Có về mặt chuyển đổi ngôn ngữ |
| `long total` và nguồn `List<Integer>` | Có | Không |
| `long total` và nguồn `int[]` | Không cần wrapper phần tử | Không |

Cả hai bộ tích lũy trong ví dụ đều sử dụng số học `long`. Điều này giúp tránh so sánh nhầm một phiên bản `int` bị tràn với một phiên bản `long` có kết quả khác.

Việc dùng `Integer value` hay `int value` trong `for-each` cần đọc theo thao tác phía sau. Chỉ khai báo biến vòng lặp là `Integer` không tự tạo boxing mới khi lấy một phần tử đã là `Integer`; mở hộp xuất hiện khi cần giá trị nguyên thủy cho phép toán. Khi khai báo `int value`, bước mở hộp nằm ở việc nhận phần tử vào biến đó.

JIT có thể tối ưu những cách viết gần nhau thành mã máy tương tự. Vì thế không chọn cú pháp vòng lặp chỉ từ một khẩu quyết rằng một bên luôn nhanh hơn; điều đáng loại bỏ trước là các phép chuyển không cần thiết do thiết kế kiểu dữ liệu.

## 3. Collection wrapper và mảng nguyên thủy là hai mô hình lưu trữ

### 3.1. Chi phí tạo dữ liệu và chi phí duyệt khác nhau

```java
List<Integer> boxed = new ArrayList<>();
for (int i = 0; i < size; i++) {
    boxed.add(i);
}
```

Mỗi `add(i)` yêu cầu một biểu diễn `Integer` theo hợp đồng của danh sách. Chi phí tạo dữ liệu này nằm ở giai đoạn xây danh sách. Nếu sau đó duyệt danh sách đã có nhiều lần, không được tính lại mọi phần tử như thể chúng vừa được boxing trong mỗi lần đọc.

Khi đo một hàm tính tổng trên dữ liệu đã có, nên tạo dữ liệu ở bước chuẩn bị ngoài phần đo. Nếu mục tiêu là đo toàn bộ đường xử lý từ tạo dữ liệu tới kết quả, cần đo cả bước tạo nhưng ghi rõ phạm vi đó.

`ArrayList` còn có mảng chứa các tham chiếu phần tử; những wrapper được giữ có thể tạo thêm nhu cầu bộ nhớ và truy cập qua tham chiếu so với dữ liệu nguyên thủy trực tiếp. Nhưng không có một số byte cố định áp dụng cho mọi JVM, cấu hình nén tham chiếu và cách tái sử dụng wrapper.

### 3.2. Integer[] vẫn chứa tham chiếu

`Integer[]` không tương đương `int[]`. Mảng wrapper vẫn giữ các tham chiếu và có thể chứa `null`; dùng phần tử trong phép toán số vẫn có thể cần unboxing.

`int[]` giữ giá trị `int`, không có phần tử `null` và có hợp đồng khác. Chuyển từ collection wrapper sang mảng nguyên thủy có thể hữu ích cho tính toán số lượng lớn, nhưng cũng có chi phí chuyển đổi và thay đổi API. Cần cân nhắc số lần sử dụng dữ liệu và yêu cầu thực tế.

### 3.3. Giữ kết quả wrapper là một yêu cầu có thể hợp lệ

Nếu thuật toán phải trả về danh sách các tổng trung gian, các giá trị cần đi vào API đối tượng:

```java
result.add(total);
```

Với `List<Long> result` và `long total`, câu lệnh này cần boxing. Đổi bộ tích lũy sang `long` vẫn tránh wrapper cho các phép tính nội bộ không cần lưu, nhưng không làm mất yêu cầu biểu diễn kết quả dưới dạng wrapper mà kiểu trả về đã đặt ra.

Khi các wrapper được giữ trong collection kết quả và kết quả được sử dụng bên ngoài, cơ hội JVM loại bỏ việc biểu diễn các đối tượng ấy có thể bị hạn chế hơn so với một wrapper trung gian không thoát ra khỏi phép tính.

## 4. Cache và JIT: không đếm đối tượng chỉ từ dấu +

### 4.1. Boxing không luôn tạo danh tính mới

API wrapper có thể dùng đối tượng được tái sử dụng. Chẳng hạn [Integer.valueOf](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Integer.html#valueOf(int)) có miền giá trị được bảo đảm dùng cache và có thể tái sử dụng thêm ngoài miền đó.

Vì vậy một phép boxing về mặt ngôn ngữ không tự là bằng chứng một đối tượng mới vừa được cấp phát. Không dùng `==` giữa các wrapper làm công cụ đo bộ nhớ; danh tính đối tượng cũng không cho biết mọi cấp phát trung gian mà JVM đã tối ưu hay loại bỏ.

### 4.2. JVM có thể loại bỏ một phần công việc

JVM tối ưu có thể inline lời gọi, phân tích việc đối tượng có thoát khỏi phạm vi sử dụng hay không và loại bỏ một số cấp phát không còn cần thiết. Những tối ưu như phân tích thoát (escape analysis) phụ thuộc đường mã, kiểu dữ liệu quan sát được và môi trường JVM.

Không có bảo đảm rằng mọi vòng lặp boxing đều được tối ưu sạch, cũng không có bảo đảm rằng mọi boxing trong mã nguồn đều trở thành cấp phát vật lý. Việc wrapper được lưu vào cấu trúc được trả về, đi qua một lời gọi khó tối ưu hoặc được dùng theo cách khác có thể ảnh hưởng khả năng tối ưu.

Tham khảo mô tả tối ưu trong [tài liệu hiệu năng HotSpot](https://docs.oracle.com/en/java/javase/25/vm/java-hotspot-virtual-machine-performance-enhancements.html). Các kết luận về một JVM cụ thể cần được xác nhận bằng đo đạc, không coi chi tiết tối ưu là hợp đồng của mã Java.

### 4.3. Áp lực GC khác với dữ liệu còn sống

Nhiều wrapper ngắn hạn có thể làm tăng tốc độ cấp phát và công việc thu gom rác. Những wrapper còn được giữ trong collection lại đóng góp vào lượng dữ liệu sống. Hai vấn đề này có thể có dấu hiệu đo khác nhau.

Một lượng wrapper được cấp phát nhiều nhưng chết nhanh không giống một collection lớn giữ mọi wrapper lâu dài. Cần đo cả lượng cấp phát và thời gian/độ trễ liên quan, thay vì chỉ nhìn dung lượng heap cuối chương trình.

## 5. Chương trình kiểm tra cùng một phép tính

Lưu thành `BoxingLoopCostDemo.java`. Chương trình này kiểm tra kết quả của các cách tổ chức dữ liệu và bộ tích lũy; nó không đo hay xếp hạng hiệu năng.

```java
import java.util.ArrayList;
import java.util.List;

public class BoxingLoopCostDemo {
    static long boxedAccumulator(List<Integer> values) {
        Long total = 0L;
        for (Integer value : values) {
            total += value;
        }
        return total;
    }

    static long primitiveAccumulator(List<Integer> values) {
        long total = 0L;
        for (int value : values) {
            total += value;
        }
        return total;
    }

    static long primitiveArray(int[] values) {
        long total = 0L;
        for (int value : values) {
            total += value;
        }
        return total;
    }

    static List<Long> prefixSums(List<Integer> values) {
        List<Long> result = new ArrayList<>(values.size());
        long total = 0L;
        for (int value : values) {
            total += value;
            result.add(total);
        }
        return result;
    }

    public static void main(String[] args) {
        int size = 10_000;
        int[] array = new int[size];
        List<Integer> boxed = new ArrayList<>(size);
        for (int i = 0; i < size; i++) {
            int value = 1000 + i;
            array[i] = value;
            boxed.add(value);
        }

        long first = boxedAccumulator(boxed);
        long second = primitiveAccumulator(boxed);
        long third = primitiveArray(array);
        List<Long> prefixes = prefixSums(boxed);

        System.out.println("boxed accumulator=" + first);
        System.out.println("primitive accumulator=" + second);
        System.out.println("primitive array=" + third);
        System.out.println("prefix count=" + prefixes.size());
        System.out.println("last prefix=" + prefixes.get(prefixes.size() - 1));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror BoxingLoopCostDemo.java
java BoxingLoopCostDemo
```

Stdout:

```text
boxed accumulator=59995000
primitive accumulator=59995000
primitive array=59995000
prefix count=10000
last prefix=59995000
```

Ba tổng bằng nhau trên cùng dãy số. Phiên bản `primitiveAccumulator` vẫn có nguồn wrapper, còn `primitiveArray` thay cả mô hình đầu vào. `prefixSums` cho thấy trường hợp kết quả thật sự cần được lưu thành `List<Long>`.

Các số được chọn và tổng đều trong phạm vi phù hợp của những kiểu dùng ở đây. Không lấy việc chương trình chạy nhanh khi nhìn bằng mắt hoặc cùng in một kết quả làm bằng chứng về số đối tượng được cấp phát.

Có thể dùng lệnh sau để xem bytecode sau khi biên dịch:

```shell
javap -c -p BoxingLoopCostDemo
```

Các lời gọi như `intValue`, `longValue` hoặc `valueOf` giúp nhận diện đường unboxing/boxing trong bytecode. Bytecode không tự chứng minh rằng các lời gọi hoặc cấp phát tương ứng còn nguyên sau khi JIT biên dịch thành mã máy.

## 6. Đo bằng JMH thay vì một lần bấm giờ

Để so sánh vòng lặp nhỏ, nên dùng một bộ đo vi mô như [OpenJDK JMH](https://github.com/openjdk/jmh). Một quy trình đo có ý nghĩa gồm:

1. **Giữ cùng hợp đồng số học.** Cùng dữ liệu đầu vào, cùng kiểu bộ tích lũy và cùng chính sách `null`/tràn số. Đừng đổi thêm thuật toán khi mục tiêu chỉ là đo boxing.
2. **Tách chuẩn bị khỏi phần cần đo.** Nếu đo duyệt danh sách sẵn có, tạo danh sách/mảng trong bước thiết lập của benchmark, không xây lại trong từng lần đo.
3. **Giữ kết quả được sử dụng.** Trả kết quả từ phương thức benchmark hoặc sử dụng cơ chế tiêu thụ kết quả thích hợp của JMH để hạn chế việc phép tính bị loại bỏ vì không có tác dụng.
4. **Dùng dữ liệu trạng thái phù hợp.** Không để toàn bộ phép tính chỉ dựa trên một hằng số mà JVM dễ tính trước.
5. **Có warmup, nhiều lần đo và nhiều tiến trình JVM độc lập.** JIT, trạng thái heap và kết quả của một lần khởi động có thể ảnh hưởng kết luận.
6. **Đo lượng cấp phát cùng thời gian.** Dùng profiler phù hợp như GC profiler của JMH; ghi rõ JDK, JVM flags, phần cứng, kích thước dữ liệu và đơn vị đo.

Các bẫy loại bỏ mã không dùng và tính trước hằng số được minh họa trong các mẫu chính thức [Dead Code](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_08_DeadCode.java) và [Constant Fold](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_10_ConstantFold.java).

Sau khi có một dự án JMH đã thiết lập và tạo được JAR benchmark theo cấu hình của nó, profiler `gc` có thể được dùng để quan sát các chỉ số như lượng byte cấp phát chuẩn hóa trên mỗi phép benchmark. Cần đọc chính đơn vị và phạm vi “một phép” của benchmark; nếu một phép chạy cả danh sách, đó không tự là chi phí cho một phần tử.

Tài liệu mẫu [JMH Profilers](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_35_Profilers.java) hướng dẫn các profiler và cách diễn giải.

Không công bố một tỷ lệ như “wrapper chậm hơn X lần” từ một lần `System.nanoTime`, đặc biệt khi có in ra console, tạo dữ liệu, chưa warmup hoặc không dùng kết quả trong đoạn đo. Cũng không ép gọi `System.gc()` rồi coi phép đo đã được chuẩn hóa.

## 7. Cải thiện theo phạm vi phù hợp

| Tình huống | Hướng xem xét |
| --- | --- |
| Biến tổng chỉ dùng để tính số trong một phương thức | Dùng bộ tích lũy nguyên thủy nếu không cần trạng thái `null` |
| Nguồn bắt buộc là List<Integer> | Chấp nhận bước mở hộp ở biên đọc; tránh boxing lại các trung gian không cần thiết |
| Tính toán nhiều lần trên dữ liệu số lớn | Cân nhắc mảng/luồng nguyên thủy sau khi tính cả chi phí chuyển đổi |
| Kết quả bắt buộc là collection wrapper | Giữ hợp đồng đầu ra; giảm những lần tạo/boxing trung gian không phục vụ kết quả |
| Dữ liệu có thể chứa null | Xác định chính sách trước khi đổi sang tính toán nguyên thủy |
| Đường mã chưa là điểm nghẽn được đo | Ưu tiên hợp đồng rõ ràng và tính đúng đắn; không thay mô hình dữ liệu chỉ vì thấy wrapper |

Với stream, một nguồn `List<Integer>` vẫn phải lấy giá trị từ wrapper. Những bước primitive như `mapToInt`/`mapToLong` có thể giữ phần tính toán tiếp theo ở dạng nguyên thủy; gọi `boxed()` lại đưa dữ liệu về wrapper. Dùng stream không tự xóa mọi chi phí biểu diễn đối tượng, và cũng không tự bảo đảm nhanh hơn vòng lặp.

Đổi từ wrapper sang nguyên thủy còn thay đổi khả năng biểu diễn thiếu dữ liệu. Không được vô tình biến `null` thành 0 chỉ để đạt một phép đo đẹp hơn; hai giá trị đó có thể khác ý nghĩa nghiệp vụ.

## 8. Tự kiểm tra

1. Dùng `long total` với nguồn `List<Integer>` có loại bỏ mọi unboxing của đầu vào không?
2. Một lệnh boxing trong mã nguồn có luôn đồng nghĩa một đối tượng mới được cấp phát vật lý không?
3. Vì sao nên tách việc tạo danh sách khỏi phép đo hàm duyệt danh sách đã có?
4. `Integer[]` có cùng mô hình lưu trữ phần tử với `int[]` không?
5. Bytecode có lời gọi `valueOf` có đủ để kết luận lượng cấp phát sau JIT không?

Đáp án:

1. Không. Nó tránh boxing lại bộ tích lũy, nhưng đọc giá trị số từ wrapper vẫn có thể cần unboxing.
2. Không. Cache và các tối ưu JVM có thể thay đổi lượng cấp phát vật lý.
3. Để phạm vi đo đúng với câu hỏi đặt ra; nếu không có thể đang so cả chi phí xây dữ liệu thay vì riêng việc duyệt.
4. Không. Một bên chứa tham chiếu wrapper, một bên chứa giá trị nguyên thủy.
5. Không. Cần đo hoặc phân tích mã thực thi trong môi trường JVM cụ thể.

Hãy nhận diện đúng nơi dữ liệu đi từ giá trị nguyên thủy sang wrapper và ngược lại, loại những bước không phục vụ hợp đồng API, rồi đo trên môi trường thực tế trước khi kết luận về cấp phát hoặc tốc độ.
