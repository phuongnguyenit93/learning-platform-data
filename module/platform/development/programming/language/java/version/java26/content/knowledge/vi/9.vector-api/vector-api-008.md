# Xử lý phần đuôi bằng mặt nạ hoặc vòng lặp vô hướng

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vì sao vòng lặp Vector API thường còn một phần tử ở cuối chưa đủ một vector.
- Dùng `VectorSpecies.loopBound()` để xử lý phần vector đầy đủ và tiếp tục bằng scalar loop.
- Dùng `VectorSpecies.indexInRange()` cùng masked load/store để xử lý cả phần đuôi bằng mask.
- Chọn cách xử lý tail phù hợp với thuật toán, khả năng đọc hiểu và kết quả benchmark.
- Kiểm tra các kích thước mảng nằm trước, đúng và sau bội số lane để phát hiện lỗi biên.
- Phân biệt Vector API incubator với preview feature khi biên dịch và chạy trên JDK 26.

## 1. Vì sao cần xử lý phần đuôi?

Một vector có số lane cố định. Số lane phụ thuộc vào kiểu phần tử và `VectorSpecies` được chọn. Trong khi đó, độ dài mảng đầu vào có thể là bất kỳ số nguyên không âm nào.

Ví dụ, một `FloatVector` có 8 lane xử lý mỗi lần 8 phần tử `float`. Nếu mảng có 19 phần tử, ta có:

- Vòng vector thứ nhất xử lý index 0 đến 7.
- Vòng vector thứ hai xử lý index 8 đến 15.
- Còn 3 phần tử ở index 16 đến 18.

Ba phần tử cuối này được gọi là *tail* hoặc phần đuôi. Nếu tiếp tục nạp một vector đầy đủ từ index 16, thao tác load sẽ vượt quá giới hạn mảng. Cần có chiến lược xử lý phần đuôi an toàn.

Có hai cách phổ biến:

1. **Vector loop + scalar tail:** dùng vector cho vùng dữ liệu đầy đủ, sau đó xử lý từng phần tử còn lại bằng vòng lặp Java thông thường.
2. **Masked vector loop:** dùng mask để chỉ bật các lane có index hợp lệ; masked load/store xử lý được cả vector đầy đủ lẫn phần đuôi.

Cả hai đều là cách hợp lệ. Không có cách nào luôn nhanh hơn trên mọi CPU và mọi kích thước dữ liệu.

## 2. Xác định số lane và giới hạn vector đầy đủ

Dùng `VectorSpecies` để biết số lane của vector được runtime chọn:

~~~java
private static final VectorSpecies<Float> SPECIES =
    FloatVector.SPECIES_PREFERRED;

int lanes = SPECIES.length();
~~~

`SPECIES_PREFERRED` chọn shape ưu tiên cho nền tảng hiện tại. Không nên giả định số lane luôn bằng 4, 8 hoặc 16 vì nó phụ thuộc kiến trúc CPU, kiểu phần tử và implementation Vector API.

`loopBound(length)` trả về giới hạn lớn nhất không vượt quá `length` mà vẫn là bội số của số lane. Nếu `length = 19` và species có 8 lane, `loopBound(19)` trả về 16.

~~~java
int upperBound = SPECIES.loopBound(length);
~~~

Như vậy:

- Các offset nhỏ hơn `upperBound` có thể nạp đủ một vector.
- Phần từ `upperBound` đến `length - 1` là tail.
- Nếu `length` chia hết cho số lane, `upperBound == length` và không có tail.
- Nếu `length` nhỏ hơn một vector, `upperBound == 0`; vòng vector được bỏ qua.

Không tự tính `upperBound` bằng phép mask bit như `length & ~(lanes - 1)`. Cách đó dựa vào giả định số lane là lũy thừa của 2. Dùng `loopBound()` để thuật toán không phụ thuộc giả định đó.

## 3. Cách 1: xử lý phần đuôi bằng scalar loop

Đây là cách đơn giản, dễ đọc và thường là điểm bắt đầu tốt:

~~~java
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorSpecies;

public final class MultiplyWithScalarTail {
    private static final VectorSpecies<Float> SPECIES =
        FloatVector.SPECIES_PREFERRED;

    static void multiply(float[] a, float[] b, float[] result) {
        if (a.length != b.length || a.length != result.length) {
            throw new IllegalArgumentException("Array lengths must match");
        }

        int upperBound = SPECIES.loopBound(a.length);
        int i = 0;

        // Xử lý vùng có thể nạp đủ một vector.
        for (; i < upperBound; i += SPECIES.length()) {
            FloatVector va = FloatVector.fromArray(SPECIES, a, i);
            FloatVector vb = FloatVector.fromArray(SPECIES, b, i);
            FloatVector vr = va.mul(vb);
            vr.intoArray(result, i);
        }

        // Xử lý phần đuôi còn lại bằng scalar.
        for (; i < a.length; i++) {
            result[i] = a[i] * b[i];
        }
    }
}
~~~

Vòng vector chỉ chạy khi còn đủ `SPECIES.length()` phần tử. Vì `upperBound` đã được làm tròn xuống theo bội số lane, các lệnh `fromArray` và `intoArray` không truy cập ngoài mảng.

Khi vòng vector kết thúc, biến `i` bằng `upperBound`. Vòng scalar tiếp tục từ đúng index này đến hết mảng. Không có phần tử nào bị bỏ qua hoặc xử lý hai lần.

Ví dụ với 19 phần tử và 8 lane:

| Giai đoạn | Index được xử lý | Cách xử lý |
|---|---|---|
| Vòng vector 1 | 0–7 | 8 lane |
| Vòng vector 2 | 8–15 | 8 lane |
| Tail | 16–18 | Scalar từng phần tử |

Với mảng rỗng hoặc ngắn hơn một vector, `upperBound` bằng 0 và chỉ vòng scalar được thực hiện. Đây là hành vi đúng, không phải trường hợp lỗi.

## 4. Cách 2: xử lý tail bằng mask

Mask biểu diễn lane nào được phép tham gia thao tác. Với `VectorSpecies`, phương thức `indexInRange(offset, limit)` tạo mask bật những lane có chỉ số nằm trong miền từ offset đến limit.

Ví dụ, species có 8 lane và offset là 16, limit là 19:

~~~text
Index toàn cục:  16  17  18  19  20  21  22  23
Mask:             1   1   1   0   0   0   0   0
                  |   |   |
                  +---+---+-- 3 lane hợp lệ
~~~

Có thể dùng mask trong cả vòng lặp:

~~~java
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorMask;
import jdk.incubator.vector.VectorSpecies;

public final class MultiplyWithMaskTail {
    private static final VectorSpecies<Float> SPECIES =
        FloatVector.SPECIES_PREFERRED;

    static void multiply(float[] a, float[] b, float[] result) {
        if (a.length != b.length || a.length != result.length) {
            throw new IllegalArgumentException("Array lengths must match");
        }

        int lanes = SPECIES.length();

        for (int i = 0; i < a.length; i += lanes) {
            VectorMask<Float> mask = SPECIES.indexInRange(i, a.length);

            FloatVector va = FloatVector.fromArray(SPECIES, a, i, mask);
            FloatVector vb = FloatVector.fromArray(SPECIES, b, i, mask);

            FloatVector vr = va.mul(vb);
            vr.intoArray(result, i, mask);
        }
    }
}
~~~

Ở vòng cuối, mask chỉ bật các lane có index nhỏ hơn độ dài mảng. Các lane không hợp lệ không được đọc từ mảng và cũng không được ghi vào mảng kết quả. Nhờ vậy, không cần vòng scalar riêng.

### Ý nghĩa của masked load và masked store

- `FloatVector.fromArray(SPECIES, a, i, mask)` nạp các phần tử tương ứng với lane được bật trong mask.
- `va.mul(vb)` thực hiện phép nhân lane-wise.
- `vr.intoArray(result, i, mask)` chỉ ghi các lane được bật.

Mask phải thuộc đúng species đang dùng. Không dùng mask của một shape hoặc kiểu phần tử khác để thao tác với vector hiện tại.

Khi mask tắt một lane, giá trị lane đó không phải dữ liệu đầu vào hợp lệ để ứng dụng dựa vào. Nếu sau đó thực hiện phép toán trên toàn vector, hãy bảo đảm các lane không hoạt động không ảnh hưởng đến kết quả được quan sát. Với ví dụ này, masked store chỉ ghi các lane hợp lệ nên kết quả ngoài miền không được sử dụng.

## 5. So sánh hai cách

| Tiêu chí | Scalar tail | Mask tail |
|---|---|---|
| Cấu trúc | Vòng vector và vòng scalar riêng | Một vòng vector có mask |
| Đọc hiểu | Rõ ràng, dễ theo dõi | Cần hiểu mask và masked operations |
| Vùng vector đầy đủ | Load/store không mask | Có mask cho cả vòng cuối và các vòng trước |
| Phần đuôi | Xử lý từng phần tử | Xử lý bằng lane hợp lệ |
| Kiểm soát biên | Dựa vào `loopBound()` | Dựa vào `indexInRange()` |
| Hiệu năng | Có thể tốt vì vòng chính không phải áp dụng mask | Có thể tiện cho kernel có miền dữ liệu phức tạp |
| Trường hợp phù hợp | Kernel đơn giản, tail ngắn | Nhiều miền hợp lệ, cần biểu diễn điều kiện theo lane |

Không nên kết luận masked loop luôn nhanh hơn vì nó tránh vòng scalar. Mask có thể làm phát sinh chi phí tạo mask hoặc hạ lệnh phụ thuộc CPU. Ngược lại, scalar tail thường rất ngắn nên chi phí của nó không đáng kể so với phần vector chính.

Hãy benchmark hai phiên bản trên workload thực tế. Với phần lớn kernel đơn giản, scalar tail là lựa chọn dễ bảo trì; masked loop đáng cân nhắc khi mask đã cần cho logic thuật toán hoặc giúp xử lý biên rõ ràng hơn.

## 6. Kiểm thử các kích thước sát ranh giới vector

Lỗi tail thường xuất hiện ở những độ dài gần bội số lane. Không chỉ kiểm tra một mảng lớn chia hết cho lane. Hãy thử:

| Kích thước | Mục đích |
|---:|---|
| 0 | Không có phần tử |
| 1 | Nhỏ hơn một vector |
| lanes - 1 | Thiếu một lane |
| lanes | Vừa đúng một vector |
| lanes + 1 | Một vector và một phần tử tail |
| 2 × lanes - 1 | Thiếu một lane ở vector thứ hai |
| 2 × lanes | Vừa đúng hai vector |
| 2 × lanes + 1 | Hai vector và một phần tử tail |

Có thể tạo kiểm thử so sánh hai chiến lược với scalar reference:

~~~java
static void verifyTailStrategies() {
    int lanes = SPECIES.length();

    int[] lengths = {
        0,
        1,
        Math.max(0, lanes - 1),
        lanes,
        lanes + 1,
        2 * lanes - 1,
        2 * lanes,
        2 * lanes + 1
    };

    for (int length : lengths) {
        float[] a = new float[length];
        float[] b = new float[length];
        float[] expected = new float[length];
        float[] scalarTail = new float[length];
        float[] maskTail = new float[length];

        for (int i = 0; i < length; i++) {
            a[i] = i * 0.5f - 2.0f;
            b[i] = i * 0.25f + 1.0f;
            expected[i] = a[i] * b[i];
        }

        MultiplyWithScalarTail.multiply(a, b, scalarTail);
        MultiplyWithMaskTail.multiply(a, b, maskTail);

        if (!Arrays.equals(expected, scalarTail)) {
            throw new AssertionError("Scalar tail failed at length " + length);
        }

        if (!Arrays.equals(expected, maskTail)) {
            throw new AssertionError("Mask tail failed at length " + length);
        }
    }
}
~~~

Đoạn kiểm thử dùng các phép nhân `float` đơn giản và so sánh cùng kết quả. Khi kernel có reduction hoặc thay đổi thứ tự phép toán dấu phẩy động, cần chọn tolerance phù hợp thay vì luôn yêu cầu so sánh bit-for-bit.

Trong test thực tế, import thêm `java.util.Arrays`. Có thể chuyển các assertion sang JUnit để CI báo rõ trường hợp thất bại. Quan trọng là kiểm tra cả kết quả và việc không truy cập ngoài biên; một test chỉ chạy với độ dài chia hết cho lane không kiểm tra được tail.

## 7. Lỗi thường gặp khi xử lý phần đuôi

### Nạp vector đầy đủ ở offset cuối

~~~java
// Sai nếu a.length - i nhỏ hơn SPECIES.length()
FloatVector v = FloatVector.fromArray(SPECIES, a, i);
~~~

Lệnh trên yêu cầu đủ lane từ offset. Nếu phần còn lại ngắn hơn vector, thao tác có thể ném `IndexOutOfBoundsException`. Dùng masked load hoặc chỉ gọi load không mask khi offset còn đủ số lane.

### Bỏ quên phần scalar tail

~~~java
int upperBound = SPECIES.loopBound(a.length);

for (int i = 0; i < upperBound; i += SPECIES.length()) {
    // Vector operation
}
// Sai nếu dừng ở đây: các phần tử từ upperBound đến cuối chưa được xử lý.
~~~

Vòng vector không tự xử lý phần còn lại. Phải có scalar tail hoặc một vòng masked tail.

### Dùng sai mask

Mask được tạo cho species cụ thể. Nếu vector là `FloatVector`, dùng `VectorMask<Float>` có cùng species. Không tái sử dụng mask từ vector có kiểu hoặc shape khác.

### Dùng giới hạn hard-code

Không cố định số lane theo CPU của máy phát triển. Dùng `SPECIES_PREFERRED` và `SPECIES.length()` để code thích ứng với nền tảng. Nếu chọn một species cố định cho mục tiêu chuyên biệt, vẫn phải xử lý đúng tail và đo trên CPU triển khai.

### Giả định mask bảo đảm tốc độ cao hơn

Mask là công cụ biểu đạt lane hợp lệ và điều kiện. Nó không phải lời hứa rằng CPU thực hiện masked operation với cùng chi phí như một vector đầy đủ. Đo hiệu năng trước khi chọn.

## 8. Cách chọn chiến lược theo workload

Ưu tiên scalar tail khi:

- Kernel có một vùng vector liên tục và phần đuôi ngắn.
- Phần xử lý tail là phép toán scalar đơn giản.
- Muốn giữ vòng chính gọn và dễ kiểm tra.
- Không cần mask cho logic khác.

Cân nhắc mask tail khi:

- Kernel đã sử dụng mask cho điều kiện dữ liệu.
- Có nhiều vùng dữ liệu hợp lệ/không hợp lệ.
- Muốn dùng cùng một cấu trúc vòng lặp cho cả phần đầy đủ và phần cuối.
- Mask giúp giảm độ phức tạp của code và vẫn có hiệu năng tốt trên CPU mục tiêu.

Trong cả hai trường hợp, cần bảo đảm:

1. Không load hoặc store ngoài giới hạn.
2. Mọi phần tử đầu ra hợp lệ được tính đúng một lần.
3. Không dùng dữ liệu của lane mask-off để tạo kết quả có thể quan sát.
4. Xử lý mảng rỗng, mảng nhỏ hơn vector và độ dài chia hết cho lane.
5. Kết quả tương đương với scalar reference theo tiêu chí chính xác của thuật toán.

## 9. Benchmark hai chiến lược

Dùng JMH để so sánh scalar tail và mask tail. Benchmark cần:

- Có cùng dữ liệu đầu vào, cùng phép toán và cùng kết quả đầu ra.
- Thử độ dài nhỏ, quanh ranh giới lane và mảng lớn.
- Có warmup và nhiều fork để JIT đạt trạng thái ổn định.
- Tránh tạo mảng mới trong vùng đo nếu mục tiêu là đo riêng kernel.
- Đưa kết quả vào Blackhole hoặc kiểm tra checksum để tránh dead-code elimination.
- Chạy trên CPU và JDK sẽ được triển khai thực tế.

Nên có ít nhất ba baseline: scalar thuần, Vector API với scalar tail và Vector API với mask tail. Scalar thuần rất quan trọng vì HotSpot có thể tự vector hóa một số vòng lặp đơn giản. Vector API không mặc định nhanh hơn auto-vectorization của JIT.

Đo cả kích thước nhỏ và lớn. Với mảng nhỏ hơn một vector, mask loop vẫn tạo một vector operation nhưng có thể không có lợi so với scalar. Với mảng rất lớn, hiệu năng có thể bị giới hạn bởi băng thông bộ nhớ, khi đó hai chiến lược tail có thể gần như không khác nhau vì phần tail chỉ chiếm tỷ lệ nhỏ.

Không dùng kết quả từ một CPU để khẳng định hiệu năng trên mọi kiến trúc. Ghi lại JDK build, CPU, số lane của species, kích thước dữ liệu, số lần lặp và cấu hình benchmark.

## 10. Biên dịch và chạy trên JDK 26

Vector API trong JDK 26 là incubator lần thứ 11 theo JEP 529, nằm trong module `jdk.incubator.vector`. Để dùng các ví dụ, cần thêm module ở cả compiler và runtime:

~~~bash
javac --add-modules jdk.incubator.vector -d out VectorTailExample.java
java --add-modules jdk.incubator.vector -cp out VectorTailExample
~~~

Nếu dự án dùng module system, khai báo:

~~~java
module com.example.vector {
    requires jdk.incubator.vector;
}
~~~

Chỉ dùng Vector API không yêu cầu `--enable-preview`; cờ cần thiết ở đây là `--add-modules jdk.incubator.vector` hoặc khai báo `requires`. Đây là incubator module, chưa phải API Java SE ổn định. Khi nâng cấp JDK, biên dịch lại, kiểm tra cảnh báo incubator và chạy lại bộ test tail trên JDK đích.

## Kết luận

Phần đuôi xuất hiện khi độ dài dữ liệu không chia hết cho số lane của vector. Dùng `VectorSpecies.loopBound()` để xử lý vùng đầy đủ bằng vector rồi tiếp tục bằng scalar loop; hoặc dùng `indexInRange()` cùng masked load/store để chỉ xử lý các lane hợp lệ. Scalar tail thường đơn giản cho kernel thông thường, còn mask hữu ích khi thuật toán đã có điều kiện theo lane hoặc nhiều vùng hợp lệ. Kiểm thử các kích thước sát bội số lane, so sánh với scalar reference và benchmark trên CPU mục tiêu trước khi quyết định. Trên JDK 26, Vector API vẫn là incubator module và cần `--add-modules jdk.incubator.vector`.

## Tài liệu tham khảo

- [JEP 529: Vector API (Eleventh Incubator), JDK 26](https://openjdk.org/jeps/529)
- [Java 26 API – VectorSpecies.loopBound](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorSpecies.html)
- [Java 26 API – VectorSpecies.indexInRange](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorSpecies.html)
- [Java 26 API – FloatVector.fromArray](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.incubator.vector/jdk/incubator/vector/FloatVector.html)
- [Java 26 API – FloatVector.intoArray](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.incubator.vector/jdk/incubator/vector/FloatVector.html)
- [Java 26 API – VectorMask](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorMask.html)
- [Java 26 API – Module jdk.incubator.vector](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.incubator.vector/module-summary.html)
