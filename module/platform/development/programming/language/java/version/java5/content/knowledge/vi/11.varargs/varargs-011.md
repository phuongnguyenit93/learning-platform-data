# Chi phí cấp phát của varargs và trường hợp nên dùng chữ ký cố định

## 1. Vì sao một lời gọi ngắn có thể tạo thêm mảng?

Varargs giúp bên gọi viết `sum(10L, 20L)` thay vì tự tạo mảng. Bên trong phương thức `sum(long... values)`, tham số `values` vẫn có kiểu `long[]`.

Khi lời gọi cần cơ chế varargs để gom các đối số rời, Java tạo mảng chứa các giá trị đó theo ngữ nghĩa của ngôn ngữ. Nhờ cú pháp gọn, chi phí chuẩn bị mảng dễ bị bỏ qua khi đọc mã.

Đoạn mã minh họa:

```java
long result = sum(10L, 20L);
```

có thể được hình dung như:

```java
long result = sum(new long[] {10L, 20L});
```

Hai đoạn thể hiện cùng ý tưởng truyền mảng đối số, không phải hai câu lệnh cần viết liên tiếp.

Tuy nhiên, **có thao tác tạo mảng trong ngữ nghĩa/bytecode không đồng nghĩa luôn có cấp phát heap tương ứng trong mã máy sau tối ưu**. JIT có thể loại bỏ một số cấp phát nếu chứng minh được việc đó không thay đổi hành vi quan sát được. Bởi vậy, không nên kết luận “varargs luôn chậm” hoặc “JIT luôn xóa hết chi phí”.

## 2. Tách các nguồn chi phí

Với một lời gọi varargs thực sự, cần xét riêng:

1. Chuẩn bị các đối số: tính toán biểu thức, tạo chuỗi hoặc tạo đối tượng nếu mã gọi yêu cầu.
2. Tạo và khởi tạo mảng đối số, rồi lưu các phần tử vào mảng.
3. Đóng hộp nếu chuyển giá trị nguyên thủy sang kiểu tham chiếu.
4. Công việc trong phương thức: duyệt phần tử, định dạng, kiểm tra, sao chép hoặc lưu dữ liệu.
5. Thu gom rác của các đối tượng tạm nếu chúng thực sự được cấp phát.

Không phải mọi lời gọi có đủ tất cả các khoản này.

| Lời gọi minh họa | Mảng đối số theo ngữ nghĩa | Đóng hộp |
| --- | --- | --- |
| `sum(10L, 20L)` với `long...` | Tạo `long[]` cho các đối số rời | Không |
| `sum()` với `long...` | Tạo mảng rỗng cho lời gọi varargs | Không |
| `sum(existing)` với `existing` là `long[]` | Truyền mảng có sẵn; không tạo mảng bao ngoài do varargs | Không |
| `sumBoxed(10L, 20L)` với `Long...` | Tạo `Long[]` | Có chuyển đổi đóng hộp |
| `pair(10L, 20L)` với hai tham số `long` | Không cần mảng đối số varargs | Không |

Đóng hộp không có nghĩa mỗi lần đều tạo một đối tượng bao mới: có thể dùng đối tượng đã tồn tại hoặc cơ chế dùng lại của kiểu bao. Dù vậy, đường đi dùng `Long...` vẫn có kiểu dữ liệu và thao tác bỏ hộp khác với `long...`.

Kích thước mảng thực tế còn phụ thuộc JVM, phần đầu đối tượng, cách căn chỉnh và loại phần tử. Không có một con số byte cố định áp dụng cho mọi JVM, cũng không có một mức chậm hơn cố định cho mọi chương trình.

## 3. Ví dụ chạy được: đường đi varargs và đường đi cố định

Lưu thành `VarargsCostDemo.java`:

```java
public class VarargsCostDemo {
    static long sum(long... values) {
        long total = 0L;
        for (long value : values) {
            total += value;
        }
        return total;
    }

    static long sumBoxed(Long... values) {
        long total = 0L;
        for (Long value : values) {
            total += value;
        }
        return total;
    }

    static long pair(long first, long second) {
        return first + second;
    }

    static long viaVarargs(long first, long second) {
        return sum(first, second);
    }

    static long viaFixed(long first, long second) {
        return pair(first, second);
    }

    static long sumFast() {
        return 0L;
    }

    static long sumFast(long value) {
        return value;
    }

    static long sumFast(long first, long second) {
        return first + second;
    }

    static long sumFast(long... values) {
        return sum(values);
    }

    public static void main(String[] args) {
        long[] existing = {10L, 20L};

        System.out.println("varargs two=" + viaVarargs(10L, 20L));
        System.out.println("fixed two=" + viaFixed(10L, 20L));
        System.out.println("existing array=" + sum(existing));
        System.out.println("fast zero=" + sumFast());
        System.out.println("fast one=" + sumFast(10L));
        System.out.println("fast two=" + sumFast(10L, 20L));
        System.out.println("fast three=" + sumFast(10L, 20L, 30L));
        System.out.println("boxed=" + sumBoxed(10L, 20L));
    }
}
```

Biên dịch và chạy trên Java 17+:

```shell
javac -encoding UTF-8 VarargsCostDemo.java
java VarargsCostDemo
```

Kết quả:

```text
varargs two=30
fixed two=30
existing array=30
fast zero=0
fast one=10
fast two=30
fast three=60
boxed=30
```

Ví dụ chứng minh kết quả tính toán và cách chọn khai báo. Nó **không phải phép đo hiệu năng**: có in ra màn hình, dữ liệu hằng và không có thiết kế đo lường để tách ảnh hưởng của JVM.

Trong `sumBoxed`, biểu thức `total += value` phải bỏ hộp `Long` thành `long`. Nếu mảng có phần tử null, phép bỏ hộp gây `NullPointerException`. Việc chọn kiểu nguyên thủy hay kiểu bao còn phải căn cứ vào ý nghĩa dữ liệu, không chỉ vào cú pháp tiện lợi.

## 4. Xem bytecode để biết trình biên dịch đã chuẩn bị gì

Sau khi biên dịch chương trình, chạy:

```shell
javap -c -p VarargsCostDemo
```

Ở `viaVarargs(long, long)`, tìm các lệnh:

- `newarray long`: tạo mảng kiểu nguyên thủy `long[]`.
- Hai lệnh `lastore`: lưu hai giá trị vào các vị trí mảng.
- `invokestatic` gọi `sum:([J)J`: truyền một mảng long và nhận một giá trị long.

Trong mô tả kiểu của JVM, `J` biểu diễn `long`, còn `[J` biểu diễn `long[]`.

Ở `viaFixed(long, long)`, các giá trị được nạp trực tiếp rồi gọi `pair:(JJ)J`. Đường đi này không có thao tác tạo mảng đối số varargs.

Trong `sumFast(long...)`, câu lệnh:

```java
return sum(values);
```

truyền thẳng mảng `values` tới `sum`; nó không tự tạo thêm một mảng nữa. Mảng đã được chuẩn bị ở bên gọi nếu lời gọi ban đầu dùng nhiều đối số rời.

Bytecode giúp giải thích cơ chế chuẩn bị đối số, nhưng không cho biết chính xác chi phí lúc chạy sau khi JIT biên dịch và tối ưu. Muốn kết luận hiệu năng thực tế phải đo trên đường đi đại diện.

## 5. JIT có thể loại bỏ chi phí nào?

HotSpot sử dụng các tối ưu như nội tuyến phương thức và phân tích thoát (escape analysis). Nếu đối tượng tạm không thoát ra ngoài phạm vi có thể phân tích và các thao tác có thể được thay thế an toàn, một số cấp phát có thể bị loại bỏ.

Ví dụ, một mảng nhỏ chỉ dùng để cộng vài giá trị rồi bị bỏ đi có thể có cơ hội tối ưu khác với một mảng được:

- lưu vào trường của đối tượng hoặc biến static;
- trả về cho bên gọi;
- chuyển tới đoạn mã mà trình tối ưu không phân tích được trong ngữ cảnh đó.

Không thoát là điều kiện hỗ trợ phân tích, không phải lời hứa rằng mọi mảng đều được loại bỏ. Kết quả còn phụ thuộc đường gọi, việc nội tuyến, kích thước mảng và JVM đang dùng.

Nếu tự sửa ví dụ thành “lưu mọi mảng vào một danh sách để đếm số mảng”, ta đã làm chúng thoát và đổi bài toán tối ưu. Phép đo đó có thể hữu ích cho trường hợp cần giữ mảng, nhưng không đại diện cho một API chỉ đọc rồi bỏ mảng.

Cũng không nên nói chung rằng “JIT chuyển mảng varargs lên stack”. Loại bỏ cấp phát hoặc thay thế đối tượng bằng các giá trị riêng là cơ chế khác với cam kết tạo nguyên một đối tượng mảng trên stack.

## 6. Khi nào nên dùng chữ ký có số tham số cố định?

### 6.1. Số lượng và vai trò của đối số vốn đã cố định

Nếu thao tác luôn nhận hai toán hạng hoặc các tham số có vai trò khác nhau, chữ ký cố định thường biểu đạt hợp đồng tốt hơn:

```java
static long pair(long first, long second) {
    return first + second;
}
```

Nếu dùng `long... values` rồi mới kiểm tra `values.length == 2`, lỗi số lượng đối số chỉ xuất hiện lúc chạy. Hai tham số tường minh giúp trình biên dịch kiểm tra ngay số lượng và giúp người đọc thấy ý nghĩa từng vị trí.

Ở tình huống này, lý do chọn chữ ký cố định trước hết là tính rõ ràng của API; việc không cần mảng varargs là lợi ích đi kèm.

### 6.2. Đường gọi rất thường xuyên với một vài số lượng điển hình

Một thư viện có thể cung cấp phiên bản cố định cho 0, 1, 2 đối số và giữ varargs cho trường hợp còn lại, như nhóm `sumFast` trong ví dụ.

Với `sumFast(10L, 20L)`, khai báo nhận hai `long` phù hợp theo lời gọi có số đối số cố định; không cần gom mảng cho tham số varargs. Với ba giá trị rời, phiên bản varargs nhận mảng được tạo cho lời gọi đó.

Cách làm này có giá trị khi:

- Đường gọi nằm trong phần xử lý được thực thi rất nhiều lần.
- Phép đo cho thấy chi phí chuẩn bị đối số có ý nghĩa so với công việc thật.
- Phần lớn lời gọi dùng một vài số lượng nhỏ, ổn định.
- Các phiên bản vẫn giữ cùng hợp đồng và kết quả.

Đổi lại, số khai báo và công sức duy trì tăng lên. Không nên tạo hàng loạt phiên bản chỉ dựa trên phỏng đoán.

### 6.3. Giữ đúng lợi ích khi cài đặt phiên bản cố định

Đoạn mã minh họa sau vẫn tự tạo mảng bên trong:

```java
static long twoButStillAllocates(long first, long second) {
    return sum(new long[] {first, second});
}
```

Bên gọi đã tránh cơ chế đóng gói varargs, nhưng thân phương thức lại yêu cầu tạo mảng. Nếu mục tiêu là giảm việc chuẩn bị mảng, hãy thực hiện phép tính trực tiếp hoặc dùng một phần triển khai không yêu cầu dựng lại mảng.

JIT có thể tối ưu đoạn mã này, nhưng không nên mô tả nó là đường đi chắc chắn không có yêu cầu tạo mảng trong mã nguồn.

## 7. Khi nào varargs vẫn là lựa chọn phù hợp?

Varargs phù hợp khi số lượng phần tử thật sự thay đổi, các phần tử có cùng vai trò và cú pháp gọi thuận tiện mang lại giá trị cho người dùng API.

Nếu một lời gọi thực hiện I/O, truy cập cơ sở dữ liệu hoặc khối tính toán lớn, chi phí chuẩn bị một mảng nhỏ có thể không đáng kể so với tổng công việc. Cần dùng phép đo để xác nhận thay vì bỏ varargs trên toàn dự án.

Nếu dữ liệu đã có dạng mảng đúng kiểu:

```java
long[] values = {10L, 20L, 30L};
long total = sum(values);
```

lời gọi không cần tạo thêm mảng đối số do varargs. Tuy nhiên, mảng `values` vẫn đã được tạo ở nơi khởi tạo; không thể từ đó kết luận toàn bộ luồng xử lý không cấp phát.

Nếu có sẵn danh sách, chuyển danh sách thành mảng trong mỗi vòng lặp cũng có thể tạo chi phí. Hãy chọn API phù hợp với dạng dữ liệu đang sở hữu, thay vì chuyển đổi qua lại chỉ để dùng một chữ ký cụ thể.

Không thay `long...` bằng `Long...` hay `Object...` chỉ để tổng quát hóa khi dữ liệu cần thiết vốn là số nguyên thủy. Mảng tham chiếu và chuyển đổi đóng hộp có đặc điểm khác, và kiểu bao còn cho phép null.

## 8. Đo hiệu năng thế nào để không rút ra kết luận sai?

Với phép đo nhỏ trên JVM, nên dùng [JMH của OpenJDK](https://github.com/openjdk/jmh) và đọc các ví dụ chính thức về khởi động JVM, loại bỏ mã không dùng và gấp hằng.

Thiết kế phép đo nên phân biệt ít nhất ba đường đi:

1. Truyền các đối số rời vào varargs.
2. Truyền cùng dữ liệu qua chữ ký cố định.
3. Truyền một mảng đã chuẩn bị sẵn vào varargs.

Nếu nghiên cứu đóng hộp, thêm một trường hợp kiểu bao riêng; không trộn nó vào kết luận về chi phí của mảng nguyên thủy.

Các điểm cần kiểm tra:

- Dùng dữ liệu đầu vào có thể thay đổi từ trạng thái phép đo, không chỉ cộng các hằng mà trình tối ưu có thể tính trước.
- Trả kết quả hoặc dùng `Blackhole` đúng cách để công việc không bị loại vì không được sử dụng.
- Có giai đoạn làm nóng, nhiều lượt đo và các tiến trình JVM độc lập (fork).
- Không đặt `System.out.println` hoặc I/O trong phần cần đo.
- Nếu nghiên cứu chi phí đóng gói ở mỗi lời gọi, hãy để việc đóng gói nằm trong phần được đo. Nếu nghiên cứu mảng đã tồn tại, chuẩn bị mảng ở ngoài phần đó.
- Đo cả thời gian hoặc thông lượng lẫn cấp phát. Profiler GC của JMH có thể hỗ trợ quan sát lượng byte cấp phát trên mỗi thao tác; một kết quả thời gian gần nhau chưa chứng minh cấp phát giống nhau.
- Ghi lại JDK, JVM, cờ chạy, phần cứng, dữ liệu, số phần tử và sai số. Không biến kết quả của một máy thành quy luật cho mọi môi trường.

Nếu JIT loại được mảng trong một trường hợp, đó là kết quả có giá trị của chính đường đi đã đo. Không cần cố ngăn tối ưu chỉ để thấy một con số cấp phát mong muốn; chỉ ngăn hoặc thay đổi ngữ cảnh khi nó phản ánh điều kiện thực tế cần nghiên cứu.

Một vòng lặp dùng `System.nanoTime()` rồi in một số tổng chưa đủ để tách chi phí JIT, gấp hằng, loại mã, thu gom rác và công việc khác. Không có số liệu đo thực tế thì nên giải thích cơ chế và điều kiện ảnh hưởng, không bịa thời gian hay tỷ lệ tăng tốc.

## 9. Lỗi dễ gặp và bài tập

| Kết luận hoặc cách làm | Điểm cần sửa |
| --- | --- |
| “Mọi lời gọi tới khai báo varargs đều tạo mảng mới” | Truyền mảng tương thích có sẵn không cần mảng đóng gói mới |
| “Mảng xuất hiện trong bytecode nên chắc chắn cấp phát lúc chạy” | Phải xét tối ưu JIT và đo cấp phát thực tế |
| “Thêm chữ ký hai tham số là tự động hết cấp phát” | Kiểm tra thân phương thức có dựng lại mảng không |
| “Dùng chung một mảng static cho mọi lời gọi để tiết kiệm” | Có thể làm các lời gọi đồng thời ghi đè dữ liệu của nhau |
| “Tổng thời gian bằng nhau nên mảng không có chi phí” | Cần xét sai số, tối ưu, tổng công việc và số byte cấp phát |

Tự thực hành:

1. Dùng `javap` tìm `newarray` trong `viaVarargs`, rồi đối chiếu với `viaFixed`.
2. Thêm `System.out.println(sumFast(existing));` vào ví dụ. Dự đoán khai báo nào được chọn: phiên bản varargs được gọi như phương thức nhận mảng có sẵn.
3. Xem `sumFast(long...)`: giải thích vì sao nó không tự tạo mảng thứ hai khi chuyển `values` cho `sum`.
4. Nếu muốn tối ưu một đoạn gọi trong vòng lặp, trước hết xác định số lượng đối số thường gặp và công việc thật trong mỗi lần gọi; sau đó mới thiết kế phép đo.

Lựa chọn API nên dựa trên ý nghĩa tham số trước, rồi dùng dữ liệu đo để quyết định có cần bổ sung đường đi cố định cho các trường hợp thường gặp hay không.

## Tài liệu đối chiếu

- [JLS §15.12.4.2 — Chuẩn bị đối số cho lời gọi varargs](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12.4.2).
- [Java HotSpot VM — Phân tích thoát và tối ưu JVM](https://docs.oracle.com/en/java/javase/21/vm/java-hotspot-virtual-machine-performance-enhancements.html).
- [OpenJDK JMH — Công cụ và các ví dụ phép đo JVM](https://github.com/openjdk/jmh).
