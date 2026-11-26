# JEP 460 trong Java 22 và trạng thái incubator cần kiểm tra ở JDK triển khai

Vector API cho phép viết các phép tính trên nhiều phần tử cùng lúc bằng Java. Khi CPU và JIT hỗ trợ, JVM có thể biên dịch những phép tính đó thành lệnh SIMD (Single Instruction, Multiple Data), giúp xử lý nhiều phần tử trong một thao tác phần cứng.

Trong Java 22, Vector API tiếp tục ở vòng incubator thứ bảy theo JEP 460. Đây không phải lần đầu API xuất hiện: quá trình incubator bắt đầu từ JDK 16. Điểm cần ghi nhớ khi học chủ đề này là API vẫn đang phát triển. Tính đến ngày 24/11/2026, JDK 27 đã có vòng incubator thứ mười hai theo JEP 537; JEP 548 cho vòng thứ mười ba mới ở trạng thái Candidate. Vì vậy, các ví dụ dưới đây dùng API có trong JDK 22 và phần cuối phân biệt rõ tính năng đã phát hành với đề xuất đang phát triển.

Sau bài học, bạn có thể:

- Giải thích SIMD và phân biệt nó với việc chạy nhiều luồng.
- Đọc được vai trò của `Vector`, `VectorSpecies`, `VectorMask` và `VectorShuffle`.
- Viết vòng lặp xử lý mảng bằng `FloatVector`, bao gồm phần tử còn dư ở cuối mảng.
- Nhận biết thay đổi của JEP 460 đối với `MemorySegment`.
- Kiểm tra module incubator trên JDK triển khai và đánh giá khi nào Vector API phù hợp.

## 1. Vector API giải quyết vấn đề gì?

Một vòng lặp thông thường thường xử lý từng phần tử:

```java
for (int i = 0; i < values.length; i++) {
    result[i] = values[i] * scale + offset;
}
```

Nếu phép tính giống nhau được áp dụng cho hàng nghìn hoặc hàng triệu phần tử, CPU có thể có khả năng xử lý nhiều giá trị trong một lệnh vector. Đây là cách hoạt động của SIMD: một lệnh thực hiện cùng một phép toán trên nhiều *lane* (làn dữ liệu) của vector.

Ví dụ, một vector có bốn lane `float` có thể biểu diễn bốn giá trị cùng lúc. Phép cộng giữa hai vector sẽ cộng lane 0 với lane 0, lane 1 với lane 1, và tương tự cho các lane còn lại. Nếu phần cứng hỗ trợ, các phép cộng này có thể được thực hiện bằng một hoặc một nhóm nhỏ lệnh SIMD.

SIMD không đồng nghĩa với đa luồng. Vector API không tự tạo thêm Java thread hay phân chia công việc lên nhiều lõi CPU. Nó biểu diễn phép toán theo nhóm dữ liệu để JVM tận dụng các thanh ghi và lệnh vector mà CPU hiện tại cung cấp. Một ứng dụng có thể kết hợp SIMD với đa luồng, nhưng đó là hai cách khai thác phần cứng khác nhau.

Vector API hữu ích nhất khi chương trình thực hiện cùng một phép toán trên dữ liệu có kiểu nguyên thủy, chẳng hạn:

- Bộ lọc và biến đổi ảnh, âm thanh hoặc tín hiệu.
- Phép toán ma trận, đại số số học và mô phỏng.
- Mã hóa, giải mã, nén dữ liệu và kiểm tra checksum.
- Tính khoảng cách, điểm số hoặc độ tương đồng trên các mảng số lớn.

API không làm cho mọi vòng lặp nhanh hơn. Vòng lặp ngắn, nhiều nhánh khó dự đoán, truy cập bộ nhớ rời rạc hoặc phải gọi các hàm scalar phức tạp có thể không nhận được lợi ích đáng kể.

## 2. JEP 460 đã thay đổi gì trong Java 22?

JEP 460 đưa Vector API vào vòng incubator thứ bảy trong JDK 22. API được tinh chỉnh nhẹ so với JDK 21; phần triển khai cũng nhận các bản sửa lỗi và cải thiện hiệu năng.

Thay đổi API đáng chú ý là khả năng truy cập vector thông qua heap `MemorySegment` được tạo từ mảng của bất kỳ kiểu dữ liệu nguyên thủy nào. Trước JDK 22, đường truy cập này bị giới hạn ở heap `MemorySegment` dựa trên `byte[]`. Từ JDK 22, các mảng như `int[]`, `float[]` hoặc `double[]` cũng có thể làm backing storage cho `MemorySegment` mà Vector API đọc hoặc ghi.

Điều này hữu ích khi chương trình kết hợp Vector API với Foreign Function & Memory API. Dữ liệu có thể được biểu diễn bằng `MemorySegment` và đưa vào phép toán vector mà không cần tự chuyển toàn bộ mảng nguyên thủy sang một `byte[]` trung gian chỉ để đáp ứng giới hạn cũ.

JEP 460 không biến Vector API thành API chuẩn của Java SE, không thêm cú pháp vector vào ngôn ngữ Java và cũng không tự động biến vòng lặp thành công việc đa luồng. Trạng thái incubator vẫn áp dụng.

## 3. Những thành phần chính của Vector API

Vector API nằm trong module `jdk.incubator.vector`, package `jdk.incubator.vector`. Các kiểu thường gặp gồm:

| Thành phần | Vai trò |
|---|---|
| `Vector<E>` | Kiểu vector cơ sở, biểu diễn một dãy lane có cùng kiểu phần tử. |
| `ByteVector`, `ShortVector`, `IntVector`, `LongVector`, `FloatVector`, `DoubleVector` | Các lớp vector dành cho từng kiểu nguyên thủy được hỗ trợ trong API JDK 22. |
| `VectorSpecies<E>` | Mô tả tổ hợp kiểu phần tử và hình dạng vector; từ đó xác định số lane và kích thước vector. |
| `VectorMask<E>` | Chọn những lane được tham gia vào một phép toán, phép đọc hoặc phép ghi. |
| `VectorShuffle<E>` | Mô tả cách sắp xếp hoặc chọn lại lane giữa các vector. |
| `VectorOperators` | Cung cấp các toán tử cho phép tính lane-wise, so sánh và một số phép toán tổng quát. |

### Lane, shape và species

Một vector chứa một số lượng cố định các lane. Mỗi lane giữ một giá trị thuộc cùng kiểu nguyên thủy, ví dụ `int` hoặc `float`. Số lane phụ thuộc vào kiểu phần tử và hình dạng vector (*vector shape*).

`VectorSpecies<E>` gom thông tin về kiểu phần tử và shape. Thay vì giả định mọi máy đều có vector 256-bit hoặc 512-bit, mã nguồn nên thường bắt đầu bằng species được nền tảng ưu tiên:

```java
private static final VectorSpecies<Float> SPECIES =
        FloatVector.SPECIES_PREFERRED;
```

`SPECIES_PREFERRED` cho phép triển khai chọn shape phù hợp với nền tảng hiện tại. Số lane có thể khác nhau giữa các máy; chương trình nên dùng `SPECIES.length()` thay vì cố định một con số.

### Phép toán lane-wise, mask và shuffle

Phần lớn phép toán phổ biến là *lane-wise*: phép toán scalar được áp dụng riêng cho từng cặp lane tương ứng. Ví dụ, `a.add(b)` cộng hai lane cùng vị trí và tạo ra vector kết quả.

`VectorMask` cho phép chỉ kích hoạt một số lane. Mask đặc biệt hữu ích khi phần tử cuối của mảng không đủ một vector đầy đủ. `VectorShuffle` dùng khi thuật toán cần hoán đổi, trích hoặc sắp xếp lại lane. Đây là các công cụ xử lý dữ liệu trong một vector; chúng không phải cơ chế đồng bộ giữa các thread.

## 4. Ví dụ: biến đổi một mảng `float` bằng Vector API

Ví dụ sau tính `output[i] = input[i] * scale + offset`. Vòng lặp vector xử lý các nhóm đủ lane; vòng lặp scalar cuối cùng xử lý phần tử còn dư.

```java
import java.util.Arrays;

import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorSpecies;

public class VectorScale {
    private static final VectorSpecies<Float> SPECIES =
            FloatVector.SPECIES_PREFERRED;

    static void scaleAndShift(
            float[] input,
            float[] output,
            float scale,
            float offset) {

        if (input.length != output.length) {
            throw new IllegalArgumentException(
                    "input and output must have the same length");
        }

        int vectorLimit = SPECIES.loopBound(input.length);
        int i = 0;

        for (; i < vectorLimit; i += SPECIES.length()) {
            FloatVector values = FloatVector.fromArray(SPECIES, input, i);
            FloatVector result = values.mul(scale).add(offset);
            result.intoArray(output, i);
        }

        // Xử lý các phần tử không đủ tạo thành một vector hoàn chỉnh.
        for (; i < input.length; i++) {
            output[i] = input[i] * scale + offset;
        }
    }

    public static void main(String[] args) {
        float[] input = new float[1_000_003];
        for (int i = 0; i < input.length; i++) {
            input[i] = i;
        }

        float[] output = new float[input.length];
        scaleAndShift(input, output, 2.0f, 1.0f);

        System.out.println(Arrays.toString(Arrays.copyOf(output, 5)));
    }
}
```

Kết quả năm phần tử đầu là `[1.0, 3.0, 5.0, 7.0, 9.0]`.

Điểm quan trọng nằm ở ba bước:

1. `FloatVector.SPECIES_PREFERRED` lấy species phù hợp với nền tảng.
2. `SPECIES.loopBound(input.length)` trả về chỉ số giới hạn lớn nhất mà tại đó vẫn còn đủ số lane cho một vector đầy đủ. Vì vậy, vòng lặp vector không đọc vượt cuối mảng.
3. `FloatVector.fromArray(...)` nạp một nhóm giá trị, `mul` và `add` thực hiện phép toán trên từng lane, rồi `intoArray(...)` ghi kết quả về mảng.

Với mảng có độ dài không chia hết cho số lane, phần tử dư được xử lý bằng vòng lặp scalar. Đây là cách đơn giản, dễ kiểm tra và phù hợp để bắt đầu. Vector API cũng hỗ trợ overload có `VectorMask` để nạp và ghi một vector cuối chỉ với các lane hợp lệ.

### Biên dịch và chạy

Với JDK có module Vector API, lưu mã trên vào `VectorScale.java`, sau đó chạy:

```bash
javac --add-modules jdk.incubator.vector VectorScale.java
java --add-modules jdk.incubator.vector VectorScale
```

Cần thêm module khi biên dịch và khi chạy ứng dụng. Thông báo cho biết đang dùng incubating module là bình thường. `--enable-preview` dành cho preview features và không phải cờ thay thế cho `--add-modules jdk.incubator.vector`.

Nếu ứng dụng dùng named module, khai báo dependency trong `module-info.java`:

```java
module example.app {
    requires jdk.incubator.vector;
}
```

## 5. Đọc và ghi `MemorySegment` với Vector API

Trong JDK 22, `MemorySegment.ofArray(...)` có thể tạo heap segment từ mảng nguyên thủy. Vector API có các phương thức như `FloatVector.fromMemorySegment(...)` và `intoMemorySegment(...)` để đọc hoặc ghi vector tại một byte offset xác định.

Ví dụ đọc một vector đầu tiên từ segment được tạo từ `float[]`:

```java
import java.lang.foreign.MemorySegment;
import java.nio.ByteOrder;

import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorSpecies;

static FloatVector loadFirstVector(float[] values) {
    VectorSpecies<Float> species = FloatVector.SPECIES_PREFERRED;
    if (values.length < species.length()) {
        throw new IllegalArgumentException("not enough values for one vector");
    }

    MemorySegment segment = MemorySegment.ofArray(values);
    return FloatVector.fromMemorySegment(
            species,
            segment,
            0,
            ByteOrder.nativeOrder());
}
```

Hàm kiểm tra mảng có đủ phần tử cho một vector theo species được chọn trước khi đọc. Khi xử lý segment ngắn hơn hoặc phần cuối không đủ lane, hãy dùng overload có mask hoặc kiểm tra giới hạn trước khi đọc. Offset của các phương thức `fromMemorySegment` và `intoMemorySegment` được tính bằng byte; thứ tự byte được truyền tường minh qua `ByteOrder`.

Điểm mới của JEP 460 là backing array của heap `MemorySegment` không còn bị giới hạn ở `byte[]`. Điều đó làm cho đường dữ liệu giữa mảng nguyên thủy, `MemorySegment` và phép toán vector linh hoạt hơn. Các quy tắc về giới hạn, phạm vi sống và quyền truy cập của `MemorySegment` vẫn phải được tuân thủ.

## 6. Khi nào nên dùng Vector API?

Vector API đáng cân nhắc khi một đoạn mã nóng thực hiện phép toán tương tự trên nhiều phần tử độc lập. Dữ liệu dạng mảng liên tục, kiểu nguyên thủy và lượng công việc đủ lớn thường là điểm bắt đầu tốt.

| Tình huống | Đánh giá |
|---|---|
| Biến đổi từng phần tử của mảng số lớn | Phù hợp để thử vector hóa. |
| Tính toán trên pixel, mẫu âm thanh hoặc tín hiệu | Phù hợp nếu các phép toán trên từng phần tử có thể biểu diễn bằng API. |
| Vòng lặp rất ngắn hoặc chỉ xử lý vài phần tử | Lợi ích có thể không bù chi phí xử lý và quản lý dữ liệu. |
| Luồng điều khiển rẽ nhánh phức tạp, phụ thuộc giữa các phần tử | Khó vector hóa hiệu quả hơn. |
| Truy cập dữ liệu ngẫu nhiên hoặc bị giới hạn bởi băng thông bộ nhớ | Vector hóa có thể không cải thiện đáng kể thời gian chạy. |

API được thiết kế để hoạt động trên nhiều kiến trúc CPU. Trên nền tảng không có hỗ trợ SIMD chuyên dụng, chương trình vẫn có thể chạy đúng nhưng không nên kỳ vọng có lợi ích hiệu năng đặc biệt. Khả năng tăng tốc còn phụ thuộc vào JDK, CPU, cách viết vòng lặp, kích thước dữ liệu và mã máy mà JIT tạo ra.

Đừng kết luận hiệu năng chỉ từ một lần chạy bằng `System.nanoTime()`. Hãy đo bằng JMH hoặc một quy trình benchmark có warm-up, nhiều lần lặp và dữ liệu đại diện. So sánh với phiên bản scalar tương đương, xác nhận kết quả đúng, thử nhiều kích thước dữ liệu và chạy trên phần cứng mục tiêu. JIT có thể tự vector hóa một số vòng lặp scalar, vì vậy cần đo cả hai phiên bản thay vì mặc định Vector API luôn nhanh hơn.

## 7. Các điểm cần kiểm tra về tính đúng đắn và khả năng chuyển đổi

- **Không cố định số lane:** dùng `SPECIES_PREFERRED`, `SPECIES.length()` và `loopBound()` để mã thích ứng với nền tảng.
- **Giữ cùng species cho các toán hạng:** các phép toán lane-wise thường yêu cầu vector đầu vào có cùng kiểu lane và shape.
- **Xử lý phần tử cuối:** dùng vòng lặp scalar hoặc mask; không đọc hay ghi một vector đầy đủ khi mảng không còn đủ phần tử.
- **Cẩn thận với phép rút gọn số thực:** phép cộng số thực không có tính kết hợp tuyệt đối do làm tròn. `reduceLanes` có thể nhóm phép cộng khác với vòng lặp scalar, vì vậy kết quả có thể sai khác ở các bit cuối.
- **Không giả định hiệu năng cố định:** species ưu tiên, lệnh máy được sinh ra và mức tăng tốc thay đổi theo JDK và CPU.
- **Không đồng nhất incubator với preview:** Vector API được cung cấp qua một incubator module. Trạng thái này có vòng đời và quy tắc sử dụng riêng; không nên xử lý nó như API Java SE đã hoàn tất.

## 8. Trạng thái incubator và cách kiểm tra JDK triển khai

Các vòng incubator là những lần tiếp tục thử nghiệm và hoàn thiện API. Tên JEP và số vòng cho biết lịch sử phát triển; chúng không có nghĩa API đã trở thành chuẩn ổn định.

| Phiên bản | JEP | Trạng thái của Vector API |
|---|---|---|
| JDK 22 | JEP 460 | Vòng incubator thứ bảy; đây là phạm vi chính của bài học. |
| JDK 26 | JEP 529 | Vòng incubator thứ mười một. |
| JDK 27 | JEP 537 | Vòng incubator thứ mười hai, đã được đưa vào JDK 27. |
| Đề xuất tiếp theo | JEP 548 | Vòng incubator thứ mười ba ở trạng thái Candidate tính đến 24/11/2026; đề xuất bổ sung vector `Float16` với lane IEEE 754 `binary16`. Đây chưa phải tính năng đã phát hành trong JDK 27. |

JEP 548 tiếp tục nêu điều kiện rằng Vector API sẽ ở trạng thái incubator cho đến khi các tính năng cần thiết của Project Valhalla có thể được cung cấp dưới dạng preview. Sau đó nhóm phát triển dự kiến điều chỉnh Vector API để sử dụng các tính năng đó và đưa API lên giai đoạn preview. Candidate là trạng thái của một đề xuất, không phải cam kết rằng tính năng đã có trong bản JDK phát hành.

Trước khi dùng Vector API trong một dự án, hãy kiểm tra chính JDK được dùng để biên dịch và chạy:

```bash
java -version
javac -version
java --describe-module jdk.incubator.vector
```

Sau đó xác nhận module có trong runtime image và cấu hình `--add-modules jdk.incubator.vector` ở cả bước biên dịch lẫn chạy. Nếu nâng cấp JDK, hãy đọc JEP và API documentation tương ứng với phiên bản mới, biên dịch lại và chạy kiểm thử trên đúng môi trường triển khai. Không suy luận rằng mã incubator sẽ giữ nguyên API chỉ vì nó đã tồn tại qua nhiều phiên bản.

Trong ứng dụng cần cam kết ổn định lâu dài, hãy cân nhắc chi phí theo dõi thay đổi API và duy trì đường chạy thay thế. Nếu Vector API chỉ mang lại mức tăng tốc nhỏ so với mã scalar, phần phụ thuộc vào incubator có thể không đáng giá. Nếu đây là điểm nóng hiệu năng đã được đo đạc, API có thể là lựa chọn phù hợp khi nhóm phát triển kiểm soát được phiên bản JDK và có kiểm thử hồi quy.

## 9. Kết luận

JEP 460 tiếp tục hoàn thiện Vector API trong JDK 22, nổi bật với việc mở rộng hỗ trợ heap `MemorySegment` được backing bởi mọi kiểu mảng nguyên thủy. Vector API cung cấp cách diễn đạt SIMD rõ ràng trong Java, nhưng hiệu năng phụ thuộc vào JIT và phần cứng, còn tính ổn định API phụ thuộc vào trạng thái incubator của từng JDK.

Khi áp dụng, hãy chọn species theo nền tảng, xử lý phần tử dư bằng loop bound hoặc mask, đo hiệu năng trên dữ liệu thực tế và kiểm tra module trong đúng JDK triển khai. Tại thời điểm 24/11/2026, Vector API vẫn là incubator: JDK 27 có vòng thứ mười hai và JEP 548 mới là đề xuất Candidate cho vòng tiếp theo.

## Tài liệu tham khảo

- [JEP 460: Vector API (Seventh Incubator)](https://openjdk.org/jeps/460)
- [JEP 537: Vector API (Twelfth Incubator)](https://openjdk.org/jeps/537)
- [JEP 548: Vector API (Thirteenth Incubator)](https://openjdk.org/jeps/548)
- [Oracle: The Arrival of Java 22](https://blogs.oracle.com/java/the-arrival-of-java-22)
- [Java 22 API: `Vector`](https://docs.oracle.com/en/java/javase/22/docs/api/jdk.incubator.vector/jdk/incubator/vector/Vector.html)
- [Java 22 API: `FloatVector`](https://docs.oracle.com/en/java/javase/22/docs/api/jdk.incubator.vector/jdk/incubator/vector/FloatVector.html)
- [Java 22 API: `VectorSpecies`](https://docs.oracle.com/en/java/javase/22/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorSpecies.html)
- [InfoQ: Java News Roundup, 23 November 2026](https://www.infoq.com/news/2026/11/java-news-roundup-nov16-2026/) — trạng thái Candidate của JEP 548 tại thời điểm biên soạn.
