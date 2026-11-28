# IndexOutOfBoundsException(long) và giới hạn phụ thuộc chuỗi thông báo

Từ Java 16, lớp **IndexOutOfBoundsException** có thêm constructor nhận chỉ số kiểu **long**. Thay đổi này cho phép API và ứng dụng làm việc với vùng dữ liệu có chỉ số hoặc offset vượt giới hạn của **int** truyền trực tiếp giá trị sai vào exception mà không phải ép kiểu gây mất dữ liệu.

Điểm quan trọng đi kèm constructor mới là giới hạn của detail message: tài liệu Java bảo đảm chỉ số được đưa vào thông điệp, nhưng **không quy định định dạng chính xác của chuỗi đó**. Vì vậy, code có thể dùng message để hỗ trợ chẩn đoán cho con người, nhưng không nên phân tích chuỗi message để lấy chỉ số, kiểm tra logic nghiệp vụ hoặc làm hợp đồng giữa các thành phần.

Java 16 cũng bổ sung các phương thức kiểm tra index và range kiểu long trong **java.util.Objects**. Đây là cách dùng ổn định để kiểm tra biên cho API có vùng dữ liệu lớn. Những kiến thức này vẫn áp dụng trong Java hiện đại, đặc biệt khi làm việc với storage abstraction hoặc Foreign Function & Memory API đã được hoàn thiện trong Java 22.

## 1. IndexOutOfBoundsException là gì?

**IndexOutOfBoundsException** là unchecked exception thuộc nhóm RuntimeException. Nó báo rằng một chỉ số hoặc khoảng dữ liệu nằm ngoài phạm vi hợp lệ của đối tượng hay vùng dữ liệu.

Ví dụ:

~~~java
int[] values = {10, 20, 30};

int value = values[3]; // ArrayIndexOutOfBoundsException
~~~

Mảng có ba phần tử nên chỉ số hợp lệ là 0, 1 và 2. Truy cập chỉ số 3 gây lỗi.

Các API khác cũng dùng IndexOutOfBoundsException khi index, offset hoặc range không hợp lệ. Exception này có hai nhóm constructor thường gặp:

| Constructor | Mục đích | Phiên bản |
| --- | --- | --- |
| IndexOutOfBoundsException() | Tạo exception không có detail message | Java 1.0 |
| IndexOutOfBoundsException(String) | Tạo exception với message do caller cung cấp | Java 1.0 |
| IndexOutOfBoundsException(int) | Đưa chỉ số sai kiểu int vào detail message | Java 9 |
| IndexOutOfBoundsException(long) | Đưa chỉ số sai kiểu long vào detail message | Java 16 |

Constructor nhận **long** là bổ sung mới của Java 16. Nó hữu ích khi chỉ số đến từ một API có miền dữ liệu được biểu diễn bằng long.

## 2. Vì sao cần constructor nhận long?

Trước Java 16, constructor nhận chỉ số của IndexOutOfBoundsException chỉ nhận int. Khi một API quản lý vùng dữ liệu có offset kiểu long gặp chỉ số không hợp lệ, code phải tự chuyển thành chuỗi hoặc ép kiểu về int.

Ép kiểu có thể làm mất giá trị:

~~~java
long index = 3_000_000_000L;

int truncated = (int) index;
System.out.println(truncated); // -1294967296
~~~

Giá trị ban đầu lớn hơn Integer.MAX_VALUE. Khi ép sang int, phần giá trị không biểu diễn được bị mất và kết quả trở thành số âm khác. Nếu dùng giá trị đã ép kiểu để tạo exception, thông tin chẩn đoán sẽ sai.

Từ Java 16, có thể truyền trực tiếp:

~~~java
long index = 3_000_000_000L;

throw new IndexOutOfBoundsException(index);
~~~

Constructor nhận long giữ được giá trị chỉ số gốc trong detail message. Không cần ép về int và cũng không cần tự ghép chuỗi chỉ để đưa index vào thông báo.

### Trường hợp sử dụng

Constructor này hữu ích với các API hoặc abstraction có index/offset kiểu long, ví dụ:

- Một storage abstraction tự quản lý vùng dữ liệu lớn.
- Một lớp đọc file hoặc vùng dữ liệu có offset kiểu long.
- Vùng nhớ native hoặc mapped memory có kích thước được biểu diễn bằng long.
- API thao tác trên MemorySegment trong Foreign Function & Memory API hiện đại.

Java 16 bổ sung long range checks cùng thời điểm với constructor này. Một động lực quan trọng là các API vùng nhớ ngoài heap cần kiểm tra offset và kích thước vượt miền int. Foreign Function & Memory API đã trở thành API chuẩn từ Java 22; khi đọc tài liệu hoặc viết ứng dụng hiện đại, hãy dùng API chuẩn của JDK đang triển khai thay vì các bản incubator cũ.

## 3. Constructor long không làm mảng Java nhận chỉ số long

Cần phân biệt kiểu của chỉ số với giới hạn của cấu trúc dữ liệu.

Theo Java Language Specification, truy cập phần tử mảng Java dùng index kiểu int. Một biểu thức truy cập mảng với index kiểu long không hợp lệ và bị lỗi biên dịch.

~~~java
int[] values = {10, 20, 30};
long index = 1L;

// int value = values[index]; // Compile-time error
~~~

Việc IndexOutOfBoundsException có constructor long không thay đổi quy tắc này. Nó chỉ cho phép biểu diễn chỉ số lỗi của những API có thể nhận chỉ số kiểu long.

Nếu một API của ứng dụng nhận long nhưng cuối cùng truy cập mảng Java, phải kiểm tra phạm vi trước rồi mới chuyển sang int:

~~~java
static int get(int[] values, long index) {
    Objects.checkIndex(index, values.length);
    return values[(int) index];
}
~~~

Sau khi check thành công, index nằm trong khoảng từ 0 đến values.length - 1. Vì độ dài mảng Java được biểu diễn bằng int, phép chuyển sang int ở bước truy cập mảng là an toàn.

Không ép kiểu trước khi kiểm tra:

~~~java
static int unsafeGet(int[] values, long index) {
    int narrowed = (int) index;
    return values[narrowed];
}
~~~

Nếu index lớn hơn miền int, phép ép kiểu có thể biến nó thành một giá trị khác. Việc kiểm tra sau khi ép kiểu sẽ không còn kiểm tra chỉ số ban đầu.

## 4. Kết hợp với Objects.checkIndex(long, long)

Java 16 bổ sung overload long cho phương thức **Objects.checkIndex**:

~~~java
long checkedIndex = Objects.checkIndex(index, length);
~~~

Phạm vi hợp lệ là khoảng nửa mở:

\[
0 \le index < length
\]

Phương thức:

- Trả lại index nếu chỉ số hợp lệ.
- Ném IndexOutOfBoundsException nếu index âm, index lớn hơn hoặc bằng length, hoặc length âm.
- Trả về long nên không làm mất kiểu của chỉ số.

Ví dụ xây dựng API đọc từ một vùng dữ liệu có chỉ số long:

~~~java
interface LongByteStore {
    long size();
    byte get(long index);
}

static byte read(LongByteStore store, long index) {
    long checked = Objects.checkIndex(index, store.size());
    return store.get(checked);
}
~~~

Ở đây LongByteStore là abstraction minh họa. API cụ thể có thể đại diện cho file, vùng nhớ hoặc một storage khác có khả năng nhận offset long.

Dùng Objects.checkIndex giúp tập trung quy tắc biên vào một phương thức chuẩn, giảm nguy cơ mỗi nơi viết một điều kiện khác nhau.

## 5. Kiểm tra một khoảng bằng Objects.checkFromToIndex

Khi API nhận điểm bắt đầu và điểm kết thúc, Java 16 cung cấp overload long:

~~~java
long checkedFrom = Objects.checkFromToIndex(fromIndex, toIndex, length);
~~~

Khoảng được hiểu theo dạng:

\[
[fromIndex,\ toIndex)
\]

Điều kiện hợp lệ:

\[
0 \le fromIndex \le toIndex \le length
\]

Trong đó:

- fromIndex được tính vào khoảng.
- toIndex là giới hạn kết thúc và không được tính vào khoảng.
- Khoảng rỗng được phép khi fromIndex bằng toIndex.
- length phải không âm.

Ví dụ:

~~~java
static long checkedRangeStart(
        long fromIndex,
        long toIndex,
        long length) {

    return Objects.checkFromToIndex(fromIndex, toIndex, length);
}
~~~

Một số trường hợp:

| fromIndex | toIndex | length | Kết quả |
| ---: | ---: | ---: | --- |
| 0 | 10 | 10 | Hợp lệ |
| 3 | 7 | 10 | Hợp lệ |
| 5 | 5 | 10 | Hợp lệ, khoảng rỗng |
| -1 | 3 | 10 | Không hợp lệ |
| 8 | 7 | 10 | Không hợp lệ |
| 0 | 11 | 10 | Không hợp lệ |

Dùng phương thức này khi API đã có hai đầu mút from/to. Không tự đổi ý nghĩa đầu mút nếu hợp đồng API đang sử dụng khoảng đóng hoặc quy ước khác.

## 6. Kiểm tra offset và size bằng Objects.checkFromIndexSize

Khi API nhận vị trí bắt đầu và số phần tử cần đọc/ghi, dùng overload long của **Objects.checkFromIndexSize**:

~~~java
long checkedFrom = Objects.checkFromIndexSize(fromIndex, size, length);
~~~

Điều kiện hợp lệ:

- fromIndex không âm.
- size không âm.
- fromIndex + size không vượt quá length.
- length không âm.

Phương thức trả về fromIndex khi hợp lệ và ném IndexOutOfBoundsException khi range không hợp lệ.

Ví dụ:

~~~java
static long validateRead(
        long offset,
        long byteCount,
        long storageSize) {

    return Objects.checkFromIndexSize(
        offset,
        byteCount,
        storageSize
    );
}
~~~

Đây là lựa chọn phù hợp cho thao tác đọc/ghi một đoạn dữ liệu, chẳng hạn offset và số byte cần xử lý.

### Tránh lỗi overflow khi tự kiểm tra range

Không nên viết kiểm tra như sau:

~~~java
if (fromIndex + size > length) {
    throw new IndexOutOfBoundsException(fromIndex);
}
~~~

Phép cộng long có thể overflow. Ví dụ fromIndex gần Long.MAX_VALUE và size dương có thể làm kết quả quay về số âm. Điều kiện so sánh sau đó có thể đánh giá sai và cho phép range không hợp lệ.

Objects.checkFromIndexSize được thiết kế để xử lý trường hợp overflow trong kiểm tra range. Hãy ưu tiên dùng phương thức này thay cho việc tự cộng rồi so sánh.

## 7. So sánh ba phương thức kiểm tra long

| Phương thức | Đầu vào | Điều kiện chính | Giá trị trả về |
| --- | --- | --- | --- |
| Objects.checkIndex(index, length) | Một chỉ số | 0 ≤ index < length | index |
| Objects.checkFromToIndex(from, to, length) | Hai đầu mút | 0 ≤ from ≤ to ≤ length | from |
| Objects.checkFromIndexSize(from, size, length) | Điểm đầu và số lượng | from ≥ 0, size ≥ 0, from + size ≤ length, xử lý overflow | from |

Các overload nhận long được bổ sung trong Java 16. Các overload int tương ứng đã có từ Java 9. Nếu dữ liệu và hợp đồng API dùng int, tiếp tục dùng overload int; nếu miền chỉ số thực sự là long, dùng overload long để tránh ép kiểu và kiểm tra thiếu chính xác.

Các phương thức kiểm tra này chỉ xác minh quan hệ số học giữa index/range và length. Chúng không tự xác minh rằng resource còn mở, vùng nhớ còn hiệu lực, thread hiện tại có quyền truy cập hay thao tác có đúng alignment. Những điều kiện đó thuộc hợp đồng của API resource tương ứng.

## 8. Giới hạn của detail message: không có định dạng chuỗi cố định

Đây là điểm quan trọng nhất của constructor long.

Tài liệu Java SE 16 mô tả constructor nhận int và long như sau: chỉ số sai được đưa vào detail message, nhưng **định dạng trình bày chính xác của detail message không được quy định**.

Điều đó có nghĩa ứng dụng có thể dựa vào việc thông tin index được đưa vào message, nhưng không được giả định chuỗi luôn có một mẫu cố định như:

~~~text
Index out of range: 3000000000
~~~

Một JDK hoặc implementation khác có thể trình bày thông tin theo định dạng khác. Nội dung message cũng có thể khác giữa các API ném exception, vì từng API có thể tự tạo detail message riêng.

Phân biệt hai trường hợp:

| Cách tạo exception | Điều có thể dựa vào |
| --- | --- |
| new IndexOutOfBoundsException(long) | Index được đưa vào message; định dạng chính xác không được cam kết |
| new IndexOutOfBoundsException(String) | Detail message do caller truyền vào được lưu làm message |
| new IndexOutOfBoundsException() | Không có detail message |

Ngay cả khi ứng dụng tự cung cấp String message, không nên dùng message làm giao thức dữ liệu. Chuỗi có thể được chỉnh sửa, dịch, thay đổi theo phiên bản hoặc thay đổi khi exception được bọc trong một exception khác.

## 9. Vì sao không nên parse getMessage()?

Ví dụ không nên làm:

~~~java
try {
    Objects.checkIndex(index, length);
} catch (IndexOutOfBoundsException exception) {
    String message = exception.getMessage();

    if (message.contains("Index out of range")) {
        // Dựa vào định dạng message để điều khiển logic
    }
}
~~~

Đoạn code phụ thuộc vào một phần văn bản không được API bảo đảm. Nếu format thay đổi, logic có thể ngừng hoạt động dù exception type và hành vi kiểm tra biên vẫn đúng.

Cách phù hợp là giữ lại dữ liệu đầu vào ở biến riêng:

~~~java
try {
    Objects.checkIndex(index, length);
} catch (IndexOutOfBoundsException exception) {
    logger.warn(
        "Index outside range: index={}, length={}",
        index,
        length
    );
    throw exception;
}
~~~

Ở đây index và length đến từ dữ liệu của chương trình, không cần trích xuất lại từ message.

Nếu cần thông tin có cấu trúc cho tầng gọi, API nên trả về kết quả hoặc dùng exception riêng có field rõ ràng:

~~~java
final class StorageIndexException
        extends IndexOutOfBoundsException {

    private final long index;
    private final long length;

    StorageIndexException(long index, long length) {
        super("Storage index is outside the valid range");
        this.index = index;
        this.length = length;
    }

    long index() {
        return index;
    }

    long length() {
        return length;
    }
}
~~~

Exception riêng giữ dữ liệu index và length thành field có thể truy cập trực tiếp. Detail message chỉ phục vụ đọc log hoặc chẩn đoán.

## 10. Kiểm thử exception đúng cách

Khi kiểm thử một phương thức sử dụng Objects.checkIndex, hãy xác nhận exception type và điều kiện gây lỗi.

Ví dụ với JUnit 5:

~~~java
@Test
void rejectsIndexOutsideRange() {
    long index = 3_000_000_000L;
    long length = 2_000_000_000L;

    assertThrows(
        IndexOutOfBoundsException.class,
        () -> Objects.checkIndex(index, length)
    );
}
~~~

Không nên kiểm tra chuỗi message mặc định:

~~~java
assertEquals(
    "Index out of range: 3000000000",
    exception.getMessage()
);
~~~

Test như vậy phụ thuộc định dạng không được đặc tả. Nó có thể thất bại khi đổi JDK dù hành vi API vẫn đúng.

Nếu đang kiểm thử exception do chính ứng dụng tạo với message riêng, có thể kiểm tra message đó như một phần hợp đồng nội bộ mà ứng dụng chủ động duy trì. Nhưng hãy phân biệt message do ứng dụng định nghĩa với message do thư viện JDK tạo.

## 11. Ví dụ tổng hợp: kiểm tra vùng dữ liệu long-indexed

Giả sử một storage có dung lượng biểu diễn bằng long. API cần đọc một vùng từ offset và số byte:

~~~java
interface ByteRegion {
    long byteSize();
    byte get(long offset);
}

static byte readByte(ByteRegion region, long offset) {
    Objects.checkIndex(offset, region.byteSize());
    return region.get(offset);
}

static void validateCopy(
        ByteRegion source,
        long sourceOffset,
        ByteRegion target,
        long targetOffset,
        long byteCount) {

    Objects.checkFromIndexSize(
        sourceOffset,
        byteCount,
        source.byteSize()
    );

    Objects.checkFromIndexSize(
        targetOffset,
        byteCount,
        target.byteSize()
    );
}
~~~

Hai lần kiểm tra đảm bảo vùng nguồn và vùng đích đều chứa đủ số byte cần xử lý. Cách kiểm tra này không cần tự cộng offset và byteCount, nên tránh lỗi overflow trong biểu thức range.

Đây là ví dụ về abstraction có long offset, không phải cách truy cập mảng Java trực tiếp. Với MemorySegment trên JDK hiện đại, API access operation cũng nhận offset long và tự áp dụng các quy tắc an toàn riêng của segment như bounds, lifetime, thread access và alignment.

## 12. Những hiểu lầm cần tránh

| Hiểu lầm | Thực tế |
| --- | --- |
| Mảng Java từ Java 16 có thể dùng index long | Mảng Java vẫn dùng index int theo JLS |
| Constructor long làm mọi API hỗ trợ dữ liệu lớn | Chỉ API có hợp đồng nhận index/range long mới tận dụng được |
| getMessage() luôn có format cố định | Constructor int/long ghi rõ format chính xác không được quy định |
| Có thể lấy index bằng cách parse message | Nên giữ index trong biến hoặc field có kiểu |
| Tự kiểm tra from + size luôn an toàn | Phép cộng long có thể overflow |
| Objects.checkFromIndexSize kiểm tra toàn bộ trạng thái resource | Nó kiểm tra số học range; lifetime, thread, alignment và quyền truy cập do API resource quản lý |
| Constructor long thay thế mọi constructor khác | String constructor vẫn hữu ích khi ứng dụng chủ động định nghĩa message |

## 13. Kết luận

Java 16 bổ sung **IndexOutOfBoundsException(long)** để biểu diễn trực tiếp chỉ số sai kiểu long. Constructor này hữu ích cho API có index hoặc offset lớn và tránh việc ép về int làm mất dữ liệu.

Đi cùng thay đổi đó, **Objects.checkIndex(long, long)**, **checkFromToIndex(long, long, long)** và **checkFromIndexSize(long, long, long)** cung cấp cách kiểm tra index/range thống nhất, trong đó kiểm tra from/size xử lý cả overflow.

Giới hạn cần nhớ là detail message của constructor int/long chỉ bảo đảm chứa index; định dạng chính xác không được cam kết. Vì vậy, hãy kiểm tra exception theo type và điều kiện, giữ dữ liệu index/length ở dạng số có cấu trúc, và chỉ dùng message cho mục đích chẩn đoán. Đồng thời, đừng nhầm long-indexed resource với mảng Java: mảng vẫn dùng int index theo đặc tả ngôn ngữ.

## Tài liệu tham khảo

- [IndexOutOfBoundsException — Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/lang/IndexOutOfBoundsException.html)
- [Objects — Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/Objects.html)
- [IndexOutOfBoundsException — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/IndexOutOfBoundsException.html)
- [Objects — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Objects.html)
- [JLS — Arrays, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-10.html)
- [JEP 454: Foreign Function & Memory API](https://openjdk.org/jeps/454)
- [MemorySegment — Java SE 22 API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html)

