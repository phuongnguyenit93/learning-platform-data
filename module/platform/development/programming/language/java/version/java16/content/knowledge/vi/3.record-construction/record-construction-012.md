# Sao chép mảng ở constructor và accessor để bảo vệ dữ liệu

> **Chương:** Khởi tạo record  
> **Học phần:** `JAVA_VERSION_JAVA16` — khám phá những cải tiến từ Java 16 vẫn hữu ích trong Java hiện đại, đặc biệt là `record`. Bài này hướng dẫn bảo vệ component kiểu mảng ở cả đầu vào constructor và đầu ra accessor, để bên gọi không thể thay đổi dữ liệu nội bộ thông qua một tham chiếu mảng dùng chung.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao component field `final` không làm cho mảng trở nên bất biến.
- Sao chép mảng đầu vào trong compact constructor bằng `clone()` hoặc `Arrays.copyOf()`.
- Override accessor để trả bản sao thay vì làm lộ mảng nội bộ.
- Phân biệt shallow copy với deep copy đối với mảng object và mảng nhiều chiều.
- Xác định chính sách null cho mảng và từng phần tử.
- Hiểu cách mảng ảnh hưởng đến `equals()`, `hashCode()` và `toString()` do record sinh tự động.
- Kiểm thử việc thay đổi mảng nguồn và mảng trả về không làm thay đổi trạng thái record.

## 1. Vì sao mảng trong record cần defensive copy?

Record phù hợp để mô hình hóa dữ liệu giá trị. Các component trong record header tạo ra component field `private final` và accessor tương ứng.

Ví dụ:

```java
public record BytePayload(byte[] bytes) {}
```

Từ khóa `final` đảm bảo field `bytes` không thể được gán lại sang một mảng khác sau khi khởi tạo. Nhưng mảng là đối tượng mutable: từng phần tử của nó vẫn có thể được sửa.

Nếu constructor lưu trực tiếp tham chiếu do bên gọi truyền vào, hai bên cùng giữ một mảng:

```java
byte[] source = {10, 20, 30};
BytePayload payload = new BytePayload(source);

source[0] = 99;

System.out.println(payload.bytes()[0]); // 99
```

Record đã bị ảnh hưởng bởi thay đổi qua tham chiếu bên ngoài. Trạng thái được biểu diễn bởi record vì thế không còn là snapshot độc lập.

Ngay cả khi constructor đã sao chép mảng đầu vào, accessor mặc định vẫn trả về tham chiếu đến mảng nội bộ. Bên gọi có thể sửa dữ liệu qua accessor:

```java
byte[] source = {10, 20, 30};
BytePayload payload = new BytePayload(source);

// Giả sử constructor đã copy input,
// nhưng accessor mặc định vẫn trả mảng nội bộ.
payload.bytes()[0] = 99;

System.out.println(payload.bytes()[0]); // 99 nếu accessor không copy
```

Để bảo vệ component kiểu mảng, cần xem xét cả hai chiều:

1. **Đầu vào:** sao chép mảng trước khi lưu vào component field.
2. **Đầu ra:** override accessor để trả một bản sao mới.

## 2. Sao chép mảng đầu vào trong compact constructor

Mảng có phương thức `clone()`. Gọi phương thức này tạo một mảng mới cùng kiểu và cùng độ dài, sao chép các phần tử sang mảng mới.

Ví dụ:

```java
import java.util.Objects;

public record BytePayload(byte[] bytes) {

    public BytePayload {
        bytes = Objects.requireNonNull(bytes, "bytes").clone();
    }
}
```

Trong compact constructor:

- `Objects.requireNonNull` xác định rõ mảng là bắt buộc.
- `clone()` tạo một mảng mới.
- Tham số ngầm `bytes` được gán lại bằng bản sao.
- Khi thân constructor kết thúc bình thường, compiler gán tham số cuối cùng vào component field.

Không viết `this.bytes = ...` trong compact constructor. Hãy gán lại tham số ngầm theo đúng cơ chế khởi tạo record.

Sau khi tạo record, việc thay đổi mảng nguồn không ảnh hưởng đến mảng đã lưu:

```java
byte[] source = {1, 2, 3};
BytePayload payload = new BytePayload(source);

source[0] = 100;

System.out.println(payload.bytes()[0]); // 1
```

Mảng đầu vào và mảng được record lưu là hai đối tượng khác nhau.

## 3. Override accessor để không làm lộ mảng nội bộ

Sao chép trong constructor mới chỉ bảo vệ chiều dữ liệu đi vào. Accessor mặc định vẫn trả về tham chiếu đến component field.

Hãy override accessor và trả một bản sao:

```java
import java.util.Objects;

public record BytePayload(byte[] bytes) {

    public BytePayload {
        bytes = Objects.requireNonNull(bytes, "bytes").clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }
}
```

Khi người gọi lấy dữ liệu:

```java
BytePayload payload = new BytePayload(new byte[] {1, 2, 3});

byte[] returned = payload.bytes();
returned[0] = 99;

System.out.println(payload.bytes()[0]); // 1
```

Accessor tạo một mảng mới mỗi lần được gọi. Người gọi có thể sửa bản sao họ nhận được, nhưng không thể sửa mảng nội bộ của record qua tham chiếu đó.

Một defensive-copy accessor không nhất thiết phải trả cùng một object array ở các lần gọi khác nhau. Hợp đồng của accessor là trả dữ liệu có cùng nội dung, không phải duy trì identity của mảng.

## 4. Ví dụ hoàn chỉnh: bảo vệ mảng byte

`byte[]` thường được dùng để biểu diễn payload nhị phân, nội dung tệp hoặc dữ liệu đã mã hóa. Một record có thể bảo vệ mảng ở cả hai chiều như sau:

```java
import java.util.Arrays;
import java.util.Objects;

public record BytePayload(byte[] bytes) {

    public BytePayload {
        bytes = Objects.requireNonNull(bytes, "bytes").clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }

    public int length() {
        return bytes.length;
    }

    public byte byteAt(int index) {
        return bytes[index];
    }

    @Override
    public String toString() {
        return "BytePayload[bytes=" + Arrays.toString(bytes) + "]";
    }
}
```

Sử dụng:

```java
byte[] input = {10, 20, 30};
BytePayload payload = new BytePayload(input);

input[0] = 99;

System.out.println(payload.byteAt(0)); // 10
System.out.println(payload.length());  // 3
System.out.println(payload);           // BytePayload[bytes=[10, 20, 30]]
```

Các phương thức `length()` và `byteAt()` cung cấp thao tác đọc mà không cần trả toàn bộ mảng nội bộ. Accessor `bytes()` vẫn tồn tại theo hợp đồng record, nhưng trả bản sao.

Nếu người gọi chỉ cần đọc một vài giá trị, các phương thức truy vấn như `length()` hoặc `byteAt()` có thể tránh cấp phát mảng mới. Nếu cần toàn bộ dữ liệu, accessor trả bản sao là ranh giới sở hữu rõ ràng.

## 5. Dùng Arrays.copyOf thay cho clone()

`Arrays.copyOf()` cũng tạo một mảng mới và sao chép các phần tử. Với mảng primitive hoặc object array cùng kiểu, có thể dùng:

```java
import java.util.Arrays;
import java.util.Objects;

public record Scores(int[] values) {

    public Scores {
        values = Arrays.copyOf(
                Objects.requireNonNull(values, "values"),
                values.length
        );
    }

    @Override
    public int[] values() {
        return Arrays.copyOf(values, values.length);
    }
}
```

Hai cách `clone()` và `Arrays.copyOf()` đều phù hợp cho defensive copy mảng một chiều:

| Cách | Đặc điểm |
| --- | --- |
| `array.clone()` | Ngắn gọn, giữ kiểu mảng runtime, sao chép đủ độ dài hiện tại. |
| `Arrays.copyOf(array, array.length)` | Nêu rõ độ dài mảng đích; thuận tiện khi muốn thay đổi độ dài trong một số tình huống. |

Khi chỉ cần bản sao cùng độ dài và cùng kiểu, `clone()` thường đơn giản hơn. `Arrays.copyOf()` hữu ích khi cần một độ dài đích cụ thể hoặc muốn thể hiện rõ thao tác sao chép trong API.

Cả hai đều là **shallow copy** đối với object array: chúng sao chép tham chiếu phần tử, không tự tạo bản sao cho từng object bên trong.

## 6. Shallow copy và deep copy đối với object array

Xét mảng chứa đối tượng mutable:

```java
// File: TagBatch.java
final class MutableTag {
    private String name;

    MutableTag(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }

    void rename(String name) {
        this.name = name;
    }
}

public record TagBatch(MutableTag[] tags) {

    public TagBatch {
        tags = java.util.Objects.requireNonNull(tags, "tags").clone();
    }

    @Override
    public MutableTag[] tags() {
        return tags.clone();
    }
}
```

Constructor và accessor đều clone mảng, nhưng các phần tử `MutableTag` vẫn là những tham chiếu cũ.

Sử dụng:

```java
MutableTag tag = new MutableTag("java");
TagBatch batch = new TagBatch(new MutableTag[] {tag});

tag.rename("changed");

System.out.println(batch.tags()[0].name()); // changed
```

Mảng bên ngoài đã được sao chép, nhưng đối tượng `MutableTag` vẫn dùng chung. Đây là shallow copy.

Nếu phần tử mutable và cần được bảo vệ, phải tạo bản sao cho từng phần tử. Ví dụ:

```java
import java.util.Objects;

// File: SafeTagBatch.java
final class MutableTag {
    private String name;

    MutableTag(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }

    void rename(String name) {
        this.name = name;
    }
}

public record SafeTagBatch(MutableTag[] tags) {

    public SafeTagBatch {
        tags = deepCopy(tags);
    }

    @Override
    public MutableTag[] tags() {
        return deepCopy(tags);
    }

    private static MutableTag[] deepCopy(MutableTag[] source) {
        Objects.requireNonNull(source, "tags");

        MutableTag[] copy = new MutableTag[source.length];

        for (int i = 0; i < source.length; i++) {
            MutableTag tag = Objects.requireNonNull(
                    source[i], "tags[" + i + "]"
            );

            copy[i] = new MutableTag(tag.name());
        }

        return copy;
    }
}
```

Trong ví dụ này:

- Constructor tạo mảng mới và tạo một `MutableTag` mới cho từng phần tử.
- Accessor tiếp tục tạo mảng mới và sao chép từng phần tử.
- Mảng nguồn và object nguồn không còn được chia sẻ với record.
- Null array và null element bị từ chối theo hợp đồng đã chọn.

Cách sao chép phải phù hợp với kiểu phần tử. Nếu một phần tử chứa collection, array hoặc object mutable khác, phương thức copy của phần tử cần xử lý các thành phần đó theo chính sách riêng.

Không có một phép `clone()` chung nào tự động tạo deep copy đúng cho mọi object graph. Việc sao chép sâu cần hiểu cấu trúc, quan hệ chia sẻ, vòng tham chiếu và ý nghĩa nghiệp vụ của từng loại object.

## 7. Mảng nhiều chiều cũng cần sao chép từng tầng

Trong Java, mảng hai chiều như `int[][]` thực chất là mảng chứa các mảng khác. Gọi `clone()` trên mảng ngoài chỉ tạo một mảng ngoài mới; các mảng con vẫn được dùng chung.

Ví dụ:

```java
int[][] source = {
        {1, 2},
        {3, 4}
};

int[][] shallow = source.clone();

source[0][0] = 99;

System.out.println(shallow[0][0]); // 99
```

Nếu muốn bảo vệ dữ liệu, cần clone từng hàng trong constructor và accessor:

```java
import java.util.Objects;

public record IntMatrix(int[][] values) {

    public IntMatrix {
        values = deepCopy(values);
    }

    @Override
    public int[][] values() {
        return deepCopy(values);
    }

    private static int[][] deepCopy(int[][] source) {
        Objects.requireNonNull(source, "values");

        int[][] copy = new int[source.length][];

        for (int i = 0; i < source.length; i++) {
            copy[i] = Objects.requireNonNull(
                    source[i], "values[" + i + "]"
            ).clone();
        }

        return copy;
    }
}
```

Phương thức trên quy định mảng ngoài và mọi hàng đều phải khác null. Nếu nghiệp vụ cho phép hàng null, có thể giữ null có chủ đích:

```java
copy[i] = source[i] == null ? null : source[i].clone();
```

Với mảng ba chiều hoặc cấu trúc lồng sâu hơn, tiếp tục sao chép từng tầng. Nếu phần tử cuối cùng là object mutable, cần thêm chính sách sao chép cho object đó.

## 8. Xác định rõ chính sách null

`clone()` không kiểm tra null. Nếu gọi `values.clone()` khi `values` là null, Java ném `NullPointerException`.

Hãy chọn một hợp đồng rõ ràng:

- **Mảng bắt buộc:** dùng `Objects.requireNonNull(values, "values")` trước khi clone.
- **Mảng được phép null:** giữ null trong component và xử lý nhất quán ở accessor cũng như các phương thức khác.
- **Mảng không null nhưng phần tử có thể null:** clone mảng vẫn giữ các phần tử null; deep-copy helper cần quy định có chấp nhận chúng hay không.

Ví dụ mảng bắt buộc nhưng cho phép mảng rỗng:

```java
import java.util.Objects;

public record Payload(byte[] data) {

    public Payload {
        data = Objects.requireNonNull(data, "data").clone();
    }

    @Override
    public byte[] data() {
        return data.clone();
    }
}
```

Mảng rỗng `new byte[0]` là hợp lệ. Null bị từ chối. Đây là hai trạng thái khác nhau và không nên tự động đổi null thành mảng rỗng trừ khi hợp đồng dữ liệu quy định như vậy.

## 9. Record có mảng: equals() và hashCode() không tự so sánh nội dung

Một chi tiết quan trọng: record sinh tự động `equals()` và `hashCode()` dựa trên các component. Với component kiểu mảng, các phương thức `equals()` và `hashCode()` của mảng kế thừa ngữ nghĩa identity từ `Object`; chúng không so sánh nội dung phần tử như `Arrays.equals()`.

Ví dụ:

```java
public record BytePayload(byte[] bytes) {
    public BytePayload {
        bytes = bytes.clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }
}
```

Hai record được tạo từ hai mảng có cùng nội dung vẫn có thể không bằng nhau:

```java
BytePayload a = new BytePayload(new byte[] {1, 2});
BytePayload b = new BytePayload(new byte[] {1, 2});

System.out.println(a.equals(b)); // false với equals mặc định của record
```

Mỗi constructor clone thành một mảng khác nhau. Vì vậy, component field của hai record tham chiếu đến hai array object khác nhau.

Nếu hợp đồng yêu cầu equality theo **nội dung mảng**, hãy override cả `equals()` và `hashCode()`:

```java
import java.util.Arrays;
import java.util.Objects;

public record BytePayload(byte[] bytes) {

    public BytePayload {
        bytes = Objects.requireNonNull(bytes, "bytes").clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }

    @Override
    public boolean equals(Object obj) {
        return this == obj
                || obj instanceof BytePayload other
                && Arrays.equals(bytes, other.bytes);
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(bytes);
    }
}
```

`Arrays.equals(byte[], byte[])` so sánh từng byte; `Arrays.hashCode(byte[])` tính hash code dựa trên nội dung tương ứng. Hai record có mảng byte cùng nội dung sẽ có equality và hash code nhất quán.

Cú pháp pattern matching cho `instanceof` trong ví dụ trên là tính năng đã được hoàn thiện từ Java 16. Nó vẫn áp dụng trong các phiên bản Java hiện đại.

Với các loại mảng khác, chọn overload tương ứng của `Arrays.equals` và `Arrays.hashCode`. Với mảng object nhiều chiều hoặc mảng lồng nhau, có thể cần `Arrays.deepEquals` và `Arrays.deepHashCode`.

Lưu ý: `Arrays.deepEquals` đệ quy qua các mảng lồng nhau, nhưng với phần tử không phải mảng, nó vẫn dựa vào `equals()` của chính phần tử đó. Nó không tự tạo deep copy và cũng không tự định nghĩa equality theo mọi thuộc tính của object mutable.

## 10. toString() mặc định của record không hiển thị nội dung mảng

Record sinh tự động `toString()`, nhưng với component kiểu mảng, biểu diễn mặc định thường là chuỗi identity của mảng, chẳng hạn `[B@...` đối với `byte[]`.

Ví dụ:

```java
public record BytePayload(byte[] bytes) {
    public BytePayload {
        bytes = bytes.clone();
    }
}
```

```java
BytePayload payload = new BytePayload(new byte[] {1, 2, 3});

System.out.println(payload);
// Có dạng BytePayload[bytes=[B@...]
```

Nếu cần log nội dung, có thể override `toString()` bằng `Arrays.toString()` hoặc `Arrays.deepToString()` tùy cấu trúc mảng:

```java
import java.util.Arrays;
import java.util.Objects;

public record BytePayload(byte[] bytes) {
    public BytePayload {
        bytes = Objects.requireNonNull(bytes, "bytes").clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }

    @Override
    public String toString() {
        return "BytePayload[bytes=" + Arrays.toString(bytes) + "]";
    }
}
```

Đây là lựa chọn về cách biểu diễn, độc lập với defensive copy. Cần cân nhắc không ghi log payload nhạy cảm hoặc dữ liệu lớn ngoài ý muốn.

## 11. Mảng có thể được truy vấn mà không cần trả bản sao

Trả clone từ accessor bảo vệ trạng thái nội bộ nhưng tạo thêm cấp phát bộ nhớ. Nếu API thường chỉ cần một phần dữ liệu, có thể cung cấp phương thức đọc hẹp hơn:

```java
public record IntSamples(int[] values) {

    public IntSamples {
        values = java.util.Objects.requireNonNull(values, "values").clone();
    }

    @Override
    public int[] values() {
        return values.clone();
    }

    public int size() {
        return values.length;
    }

    public int get(int index) {
        return values[index];
    }

    public boolean isEmpty() {
        return values.length == 0;
    }
}
```

Các phương thức `size()`, `get()` và `isEmpty()` đọc trực tiếp field nội bộ nhưng chỉ trả giá trị primitive. Bên gọi không nhận được tham chiếu đến mảng gốc.

Nếu cần truy cập toàn bộ dữ liệu thường xuyên, có thể cân nhắc một API truyền dữ liệu theo từng phần hoặc dùng kiểu collection/abstraction phù hợp. Đừng bỏ defensive copy chỉ vì lo ngại cấp phát; hãy đo hiệu năng trong ngữ cảnh thực tế trước khi thay đổi hợp đồng bảo vệ dữ liệu.

## 12. Kiểm thử defensive copy ở constructor và accessor

Một bộ test cần kiểm tra cả hai hướng aliasing:

1. Thay đổi mảng nguồn sau khi tạo record không làm thay đổi component.
2. Thay đổi mảng trả về từ accessor không làm thay đổi component.
3. Null bị xử lý đúng theo hợp đồng.
4. Equality theo nội dung hoạt động nếu record đã override `equals()` và `hashCode()`.

Ví dụ với JUnit Jupiter:

```java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class BytePayloadTest {

    @Test
    void copiesInputArray() {
        byte[] source = {1, 2, 3};

        BytePayload payload = new BytePayload(source);
        source[0] = 99;

        assertArrayEquals(new byte[] {1, 2, 3}, payload.bytes());
    }

    @Test
    void accessorReturnsIndependentArray() {
        BytePayload payload = new BytePayload(new byte[] {1, 2, 3});

        byte[] returned = payload.bytes();
        returned[1] = 99;

        assertArrayEquals(new byte[] {1, 2, 3}, payload.bytes());
    }

    @Test
    void rejectsNullArray() {
        assertThrows(
                NullPointerException.class,
                () -> new BytePayload(null)
        );
    }

    @Test
    void comparesArrayContentsWhenValueEqualityIsImplemented() {
        BytePayload first = new BytePayload(new byte[] {1, 2});
        BytePayload second = new BytePayload(new byte[] {1, 2});

        assertEquals(first, second);
        assertEquals(first.hashCode(), second.hashCode());
    }
}
```

Test equality cuối chỉ đúng với phiên bản `BytePayload` đã override `equals()` và `hashCode()` ở mục 9. Nếu dùng record chỉ clone mảng mà giữ equality mặc định, hai đối tượng với hai array khác nhau sẽ không bằng nhau theo nội dung.

Với mảng object hoặc mảng nhiều chiều, cần thêm test thay đổi phần tử mutable và hàng con sau khi tạo record, cũng như thay đổi object nhận được qua accessor.

## 13. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Chỉ khai báo component field `final` | Phần tử mảng vẫn có thể bị thay đổi. | Clone mảng trong constructor. |
| Clone ở constructor nhưng dùng accessor mặc định | Bên gọi vẫn sửa được mảng nội bộ. | Override accessor và trả clone. |
| Clone object array rồi nghĩ đã deep copy | Các object phần tử vẫn dùng chung tham chiếu. | Sao chép từng phần tử mutable. |
| Clone mảng ngoài của `int[][]` | Các hàng bên trong vẫn dùng chung. | Clone từng hàng. |
| Quên kiểm tra null trước `clone()` | Ném `NullPointerException` không có thông điệp rõ. | Dùng `Objects.requireNonNull`. |
| Chỉ override accessor nhưng không copy input | Nguồn bên ngoài vẫn sửa được mảng đã lưu. | Copy cả đầu vào lẫn đầu ra. |
| Nghĩ record tự so sánh nội dung array | `equals()` mặc định dùng equality identity của array. | Override bằng `Arrays.equals` và `Arrays.hashCode`. |
| Nghĩ `toString()` mặc định in nội dung mảng | Thường chỉ hiện chuỗi identity như `[B@...`. | Dùng `Arrays.toString` hoặc `Arrays.deepToString`. |
| Deep copy object graph bằng một helper chung tùy tiện | Có thể làm sai aliasing, vòng tham chiếu hoặc ngữ nghĩa object. | Xây dựng copy theo kiểu dữ liệu và hợp đồng cụ thể. |
| Trả array nội bộ để tránh cấp phát | Làm lộ trạng thái mutable của record. | Cung cấp accessor clone hoặc phương thức truy vấn hẹp. |

## 14. Bài tập tự luyện

### Bài 1: Bảo vệ mảng byte

Viết record `FileDigest(byte[] bytes)` sao cho:

- Mảng không được null.
- Constructor sao chép mảng đầu vào.
- Accessor trả về bản sao.
- Bên gọi thay đổi mảng nguồn hoặc mảng nhận được không làm thay đổi record.

**Đáp án tham khảo:**

```java
import java.util.Objects;

public record FileDigest(byte[] bytes) {
    public FileDigest {
        bytes = Objects.requireNonNull(bytes, "bytes").clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }
}
```

### Bài 2: Phân biệt shallow copy

Một record nhận `String[] names` và dùng `names.clone()` trong constructor. Cách này có bảo vệ được từng chuỗi không?

**Đáp án:** Có. `String` là kiểu bất biến, nên việc sao chép cấu trúc mảng là đủ để ngăn thay đổi phần tử qua alias của mảng nguồn. Nếu phần tử là object mutable, clone mảng chỉ sao chép tham chiếu và chưa đủ.

### Bài 3: Sao chép mảng hai chiều

Viết helper sao chép `int[][]` để cả mảng ngoài và từng hàng đều độc lập.

**Đáp án tham khảo:**

```java
private static int[][] deepCopy(int[][] source) {
    java.util.Objects.requireNonNull(source, "source");

    int[][] copy = new int[source.length][];
    for (int i = 0; i < source.length; i++) {
        copy[i] = java.util.Objects.requireNonNull(
                source[i], "row " + i
        ).clone();
    }
    return copy;
}
```

### Bài 4: Equality theo nội dung

Hai record `BytePayload` được tạo từ hai mảng byte khác nhau nhưng có cùng nội dung. Vì sao equality mặc định có thể trả false?

**Đáp án:** Mỗi constructor clone thành một array object riêng. Array dùng equality theo identity, vì vậy component array của hai record không bằng nhau theo `equals()` mặc định. Nếu cần value equality, override `equals()` với `Arrays.equals()` và `hashCode()` với `Arrays.hashCode()`.

### Bài 5: Accessor có nên trả mảng nội bộ?

Một API muốn tối ưu hiệu năng bằng cách trả trực tiếp array component. Hãy nêu rủi ro và một cách thiết kế thay thế.

**Đáp án:** Người gọi có thể sửa mảng nội bộ và làm thay đổi trạng thái record. Hãy trả clone hoặc cung cấp các phương thức đọc hẹp như `size()`, `get(index)`, `byteAt(index)` để tránh lộ tham chiếu mutable.

## Ghi nhớ

Mảng là mutable dù component field của record là `final`. Hãy clone mảng đầu vào trong compact hoặc canonical constructor và override accessor để trả bản sao. `clone()` và `Arrays.copyOf()` chỉ sao chép cấu trúc; object array hoặc mảng nhiều chiều cần sao chép từng phần tử/tầng nếu dữ liệu bên trong mutable. Record có mảng cũng không tự so sánh nội dung bằng `equals()` và `hashCode()` mặc định; nếu cần value equality, hãy dùng các phương thức `Arrays` phù hợp. Kiểm thử cả thay đổi từ mảng nguồn lẫn mảng trả về để xác nhận record giữ được trạng thái độc lập.

## Tài liệu tham khảo

- [Java API — Object.clone](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Object.html#clone()).
- [Java API — Arrays.copyOf](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Arrays.html#copyOf(T%5B%5D,int)).
- [Java API — Arrays.equals and Arrays.hashCode](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Arrays.html).
- [Java Language Specification — Java SE 26, `8.10` Record Classes](https://docs.oracle.com/javase/specs/jls/se26/html/jls-8.html#jls-8.10).
- [JEP 395 — Records (hoàn thiện trong Java 16)](https://openjdk.org/jeps/395).
