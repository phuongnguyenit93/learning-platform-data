# Kết hợp equals, compare và mismatch đúng mục đích

Ba nhóm phương thức `Arrays.equals`, `Arrays.compare` và `Arrays.mismatch` cùng làm việc với nội dung mảng, nhưng trả lời ba câu hỏi khác nhau. Chọn đúng phương thức giúp mã rõ ý định, dễ chẩn đoán dữ liệu và tránh nhầm lẫn giữa “bằng nhau theo equals” với “bằng nhau theo thứ tự so sánh”.

- `equals` trả về boolean: hai mảng có cùng nội dung theo quy tắc equality đang dùng hay không?
- `compare` trả về số âm, 0 hoặc số dương: mảng nào đứng trước theo thứ tự từ điển?
- `mismatch` trả về vị trí khác đầu tiên hoặc -1: dữ liệu bắt đầu khác nhau ở đâu?

Từ Java 9, cả ba nhóm API có overload nhận phạm vi của hai mảng. Có thể kết hợp chúng để kiểm tra một vùng, xác định thứ tự của vùng đó và báo chính xác vị trí khác nhau mà không phải sao chép mảng con.

## 1. Bắt đầu từ câu hỏi cần trả lời

Nếu chỉ cần kiểm tra hai mảng có bằng nhau hay không, dùng `Arrays.equals`:

~~~java
boolean same = Arrays.equals(expected, actual);
~~~

Nếu cần sắp xếp mảng hoặc xác định mảng nào có thứ tự từ điển nhỏ hơn, dùng `Arrays.compare`:

~~~java
int order = Arrays.compare(first, second);

if (order < 0) {
    System.out.println("first đứng trước second");
} else if (order > 0) {
    System.out.println("first đứng sau second");
} else {
    System.out.println("hai mảng bằng nhau theo thứ tự so sánh");
}
~~~

Nếu cần tìm điểm dữ liệu khác đầu tiên để hiển thị lỗi hoặc ghi log, dùng `Arrays.mismatch`:

~~~java
int index = Arrays.mismatch(expected, actual);

if (index == -1) {
    System.out.println("Không có khác biệt");
} else {
    System.out.println("Khác nhau tại index " + index);
}
~~~

Không nên kiểm tra `order == -1` hoặc `order == 1`. Hợp đồng của compare chỉ bảo đảm dấu âm, 0 hoặc dấu dương; giá trị khác 0 có thể có độ lớn bất kỳ.

## 2. Mối quan hệ giữa equals, compare và mismatch

Với mảng primitive, ba phương thức sử dụng quy tắc so sánh tương ứng cho từng kiểu. Với mảng đối tượng, cần chú ý cách xác định hai phần tử có tương đương hay không:

- `Arrays.equals(Object[], Object[])` so sánh từng cặp phần tử bằng quy tắc `Objects.equals`, tức gọi `equals` của phần tử khác null.
- `Arrays.compare(T[], T[])` dùng thứ tự tự nhiên `Comparable.compareTo`.
- `Arrays.mismatch(Object[], Object[])` tìm phần tử đầu tiên khác nhau theo equality của phần tử.
- Các overload nhận Comparator dùng Comparator để quyết định thứ tự hoặc tính tương đương của các phần tử.

Vì `equals` và `compareTo` của một lớp không bắt buộc phải nhất quán với nhau, `Arrays.compare(a, b) == 0` không phải lúc nào cũng có nghĩa là `Arrays.equals(a, b)` trả về true.

### Ví dụ quan trọng với BigDecimal

`BigDecimal.equals` xét cả giá trị và scale. `BigDecimal.compareTo` so sánh giá trị số và bỏ qua khác biệt scale:

~~~java
BigDecimal[] a = {new BigDecimal("1.0")};
BigDecimal[] b = {new BigDecimal("1.00")};

System.out.println(Arrays.equals(a, b));   // false
System.out.println(Arrays.compare(a, b));  // 0
System.out.println(Arrays.mismatch(a, b)); // 0
~~~

Hai phần tử có cùng giá trị số, nên compare trả 0. Tuy nhiên, scale khác nhau khiến equals trả false và mismatch chỉ ra khác biệt ở chỉ số 0.

Đây không phải lỗi của Arrays. Hai API đang áp dụng hai định nghĩa tương đương khác nhau. Khi dữ liệu cần được so sánh theo giá trị số, hãy truyền cùng một Comparator cho các overload hỗ trợ Comparator:

~~~java
Comparator<BigDecimal> numericOrder = BigDecimal::compareTo;

boolean sameNumerically = Arrays.equals(a, b, numericOrder);
int numericComparison = Arrays.compare(a, b, numericOrder);
int numericMismatch = Arrays.mismatch(a, b, numericOrder);
~~~

Với Comparator này, hai mảng được xem là tương đương theo giá trị số: equals trả true, compare trả 0 và mismatch trả -1.

Comparator cần có quy tắc nhất quán, ổn định và phù hợp với ý nghĩa nghiệp vụ. Nếu Comparator không tạo được một thứ tự hợp lệ hoặc có tác dụng phụ, kết quả sắp xếp và so sánh có thể khó dự đoán.

## 3. Dùng cùng Comparator để kiểm tra, sắp xếp và tìm khác biệt

Với mảng đối tượng, nếu nghiệp vụ có một thứ tự riêng, nên dùng cùng Comparator trong các thao tác liên quan:

~~~java
Comparator<String> ignoreCase = String.CASE_INSENSITIVE_ORDER;

boolean same = Arrays.equals(first, second, ignoreCase);
int order = Arrays.compare(first, second, ignoreCase);
int mismatch = Arrays.mismatch(first, second, ignoreCase);
~~~

Khi Comparator trả 0 cho hai phần tử tương ứng:

- `equals(..., comparator)` xem cặp phần tử đó là tương đương.
- `compare(..., comparator)` xem cặp phần tử đó không tạo ra khác biệt về thứ tự.
- `mismatch(..., comparator)` tiếp tục sang phần tử kế tiếp.

Nếu Comparator bỏ qua chữ hoa/chữ thường, hai mảng `["Java"]` và `["java"]` được xem là bằng nhau theo Comparator, dù `String.equals` trả false.

Đừng trộn lẫn các quy tắc trong cùng một luồng xử lý. Ví dụ, kiểm tra bằng Comparator không phân biệt hoa thường rồi lại tìm mismatch bằng overload không Comparator có thể báo khác biệt mà bước kiểm tra trước đó đã coi là không đáng kể.

## 4. Kết hợp range overload để kiểm tra và chẩn đoán một vùng

Java 9 bổ sung các overload nhận hai đoạn theo quy ước khoảng nửa mở `[fromIndex, toIndex)`:

~~~java
Arrays.equals(a, fromA, toA, b, fromB, toB);
Arrays.compare(a, fromA, toA, b, fromB, toB);
Arrays.mismatch(a, fromA, toA, b, fromB, toB);
~~~

Một quy trình so sánh vùng dữ liệu có thể viết như sau. Ví dụ này xử lý được cả trường hợp hai đoạn có độ dài khác nhau:

~~~java
int fromA = 2;
int toA = 6;
int fromB = 4;
int toB = 8;

int lengthA = toA - fromA;
int lengthB = toB - fromB;
boolean same = Arrays.equals(a, fromA, toA, b, fromB, toB);

if (same) {
    System.out.println("Hai đoạn bằng nhau");
} else {
    int mismatch = Arrays.mismatch(a, fromA, toA, b, fromB, toB);
    int commonLength = Math.min(lengthA, lengthB);

    if (mismatch < commonLength) {
        int absoluteA = fromA + mismatch;
        int absoluteB = fromB + mismatch;
        System.out.println(
            "Khác tại a[" + absoluteA + "] và b[" + absoluteB + "]"
        );
    } else if (lengthA > lengthB) {
        System.out.println(
            "Đoạn A còn phần tử tại a[" + (fromA + mismatch) + "]"
        );
    } else {
        System.out.println(
            "Đoạn B còn phần tử tại b[" + (fromB + mismatch) + "]"
        );
    }
}
~~~

Khi dùng range overload, mismatch trả về chỉ số tương đối tính từ đầu đoạn. Muốn tìm chỉ số trong mảng gốc, cộng kết quả với `fromIndex` tương ứng.

Nếu hai đoạn có phần chung giống nhau nhưng độ dài khác nhau, mismatch trả về độ dài của đoạn ngắn hơn. Giá trị đó không chỉ ra một phần tử khác ở cả hai phía; nó cho biết điểm mà một đoạn kết thúc sớm hơn. Vì vậy, cần so sánh độ dài hai đoạn khi diễn giải mismatch.

### Dùng compare sau mismatch

Khi hai vùng khác nhau, compare cho biết vùng nào đứng trước theo thứ tự từ điển. Mismatch cho biết điểm khác đầu tiên:

~~~java
int order = Arrays.compare(a, fromA, toA, b, fromB, toB);
int mismatch = Arrays.mismatch(a, fromA, toA, b, fromB, toB);

if (order == 0) {
    System.out.println("Hai vùng tương đương theo thứ tự so sánh");
} else {
    System.out.println(
        "Vùng A " + (order < 0 ? "đứng trước" : "đứng sau")
        + " vùng B; điểm khác tương đối=" + mismatch
    );
}
~~~

Nếu chỉ cần xác định có bằng nhau hay không, không cần gọi cả ba API. Chỉ gọi thêm mismatch hoặc compare khi kết quả đó thực sự cần cho chẩn đoán hay quyết định tiếp theo.

## 5. So sánh dữ liệu byte: equality, vị trí khác và thứ tự unsigned

Trong dữ liệu nhị phân, một byte Java có dấu nhưng nội dung thường được hiểu theo miền unsigned 0 đến 255. Khi cần so sánh thứ tự byte theo cách đó, dùng `Arrays.compareUnsigned`.

Equality của byte không thay đổi theo cách diễn giải signed hay unsigned: cùng một mẫu bit vẫn là cùng một byte. Vì vậy có thể dùng `Arrays.equals` hoặc `Arrays.mismatch` để kiểm tra và tìm vị trí khác; dùng `compareUnsigned` khi cần thứ tự unsigned.

~~~java
byte[] expected = {(byte) 0x10, (byte) 0xFF, 0x20};
byte[] actual = {(byte) 0x10, 0x01, 0x20};

boolean same = Arrays.equals(expected, actual);
int mismatch = Arrays.mismatch(expected, actual);
int unsignedOrder = Arrays.compareUnsigned(expected, actual);

System.out.println(same);             // false
System.out.println(mismatch);         // 1
System.out.println(unsignedOrder > 0); // true
~~~

Ở vị trí 1, byte `0xFF` có giá trị unsigned 255, lớn hơn `0x01`. `compareUnsigned` phản ánh thứ tự đó, còn mismatch vẫn chỉ ra vị trí đầu tiên có mẫu byte khác nhau.

Với mảng primitive khác, dùng `compare` nếu ý nghĩa dữ liệu là số có dấu thông thường. Chỉ chọn `compareUnsigned` khi định dạng dữ liệu quy định cách diễn giải không dấu.

## 6. Dùng compare để sắp xếp các mảng

`Arrays.compare` có thể làm Comparator cho các mảng cùng kiểu phần tử. Khi sắp xếp một danh sách các mảng, thứ tự từ điển so sánh phần tử đầu tiên, sau đó lần lượt các phần tử tiếp theo nếu phần đầu bằng nhau:

~~~java
List<int[]> rows = new ArrayList<>();
rows.add(new int[] {2, 5});
rows.add(new int[] {1, 9});
rows.add(new int[] {1, 3});
rows.add(new int[] {1, 3, 0});

rows.sort(Arrays::compare);
~~~

Sau khi sắp xếp, thứ tự là:

1. `[1, 3]`
2. `[1, 3, 0]`
3. `[1, 9]`
4. `[2, 5]`

Hai mảng có cùng phần đầu sẽ được so sánh ở phần tử khác đầu tiên. Nếu một mảng là tiền tố của mảng kia, mảng ngắn hơn đứng trước.

Với mảng đối tượng cần quy tắc riêng, truyền Comparator rõ ràng:

~~~java
Comparator<String[]> byCaseInsensitiveOrder =
    (left, right) -> Arrays.compare(
        left,
        right,
        String.CASE_INSENSITIVE_ORDER
    );

rowsOfNames.sort(byCaseInsensitiveOrder);
~~~

Không dùng thứ tự tự nhiên khi lớp phần tử không triển khai Comparable. Nếu kiểu dữ liệu không có thứ tự tự nhiên phù hợp, hãy cung cấp Comparator.

## 7. Null và biên phạm vi

Các API không có cùng hợp đồng xử lý null:

- `Arrays.equals(null, null)` trả về true.
- `Arrays.equals(null, nonNullArray)` trả về false.
- `Arrays.compare` và `Arrays.mismatch` yêu cầu mảng khác null; truyền null gây NullPointerException.
- Các overload theo đoạn cũng yêu cầu mảng hợp lệ và phạm vi nằm trong độ dài mảng.

Với hai đoạn, `fromIndex` được tính vào, `toIndex` không được tính vào. Nếu `fromIndex > toIndex`, API ném IllegalArgumentException. Nếu chỉ số âm hoặc vượt quá độ dài mảng, API ném lỗi chỉ số ngoài phạm vi.

Nếu dữ liệu đầu vào có thể null, hãy quyết định rõ null có ý nghĩa là “không có mảng”, “mảng rỗng” hay dữ liệu không hợp lệ. Không tự thay null bằng mảng rỗng nếu nghiệp vụ cần phân biệt hai trạng thái.

## 8. Ví dụ Java chạy được

Ví dụ dưới đây thể hiện khác biệt giữa equality và thứ tự tự nhiên của BigDecimal, sau đó dùng Comparator thống nhất, chẩn đoán đoạn dữ liệu và so sánh byte unsigned.

~~~java
import java.math.BigDecimal;
import java.util.Arrays;
import java.util.Comparator;

public class ArrayComparisonWorkflow {
    public static void main(String[] args) {
        BigDecimal[] first = {new BigDecimal("1.0"), new BigDecimal("2.00")};
        BigDecimal[] second = {new BigDecimal("1.00"), new BigDecimal("2.0")};

        System.out.println("natural equals=" + Arrays.equals(first, second));
        System.out.println("natural compare="
            + Arrays.compare(first, second));
        System.out.println("natural mismatch="
            + Arrays.mismatch(first, second));

        Comparator<BigDecimal> numeric = BigDecimal::compareTo;
        System.out.println("numeric equals="
            + Arrays.equals(first, second, numeric));
        System.out.println("numeric compare="
            + Arrays.compare(first, second, numeric));
        System.out.println("numeric mismatch="
            + Arrays.mismatch(first, second, numeric));

        int[] expected = {8, 10, 20, 30, 40, 9};
        int[] actual = {7, 10, 20, 99, 40, 6};
        int mismatch = Arrays.mismatch(
            expected, 1, 5,
            actual, 1, 5
        );
        int order = Arrays.compare(
            expected, 1, 5,
            actual, 1, 5
        );
        System.out.println("range mismatch=" + mismatch);
        System.out.println("range absolute index=" + (1 + mismatch));
        System.out.println("range first before second=" + (order < 0));

        byte[] high = {(byte) 0xFF};
        byte[] low = {0x01};
        System.out.println("unsigned mismatch="
            + Arrays.mismatch(high, low));
        System.out.println("unsigned first greater="
            + (Arrays.compareUnsigned(high, low) > 0));
    }
}
~~~

Biên dịch và chạy với Java 17 trở lên:

~~~shell
javac --release 17 -Xlint:all ArrayComparisonWorkflow.java
java ArrayComparisonWorkflow
~~~

Kết quả stdout chính xác:

~~~text
natural equals=false
natural compare=0
natural mismatch=0
numeric equals=true
numeric compare=0
numeric mismatch=-1
range mismatch=2
range absolute index=3
range first before second=true
unsigned mismatch=0
unsigned first greater=true
~~~

Giải thích:

1. BigDecimal có scale khác nhau nên equals trả false. Thứ tự tự nhiên dùng compareTo, xem hai giá trị số là tương đương nên compare trả 0.
2. mismatch không dùng compareTo tự nhiên ở overload không Comparator; nó phát hiện khác biệt theo equals tại vị trí 0.
3. Khi truyền Comparator dùng compareTo, equals theo Comparator trả true và mismatch trả -1.
4. Hai đoạn số nguyên bắt đầu ở chỉ số 1. Phần tử khác đầu nằm ở vị trí tương đối 2, tương ứng chỉ số tuyệt đối 3.
5. Với byte, mẫu bit khác nhau tại chỉ số 0. compareUnsigned cho biết 255 lớn hơn 1.

## 9. Chọn quy trình phù hợp

| Yêu cầu | Quy trình |
|---|---|
| Chỉ kiểm tra hai mảng bằng nhau | `Arrays.equals(a, b)` |
| Kiểm tra rồi báo vị trí khác | `equals`, sau đó `mismatch` nếu cần |
| Cần cả vị trí khác và thứ tự | `mismatch` và `compare` với cùng quy tắc phần tử |
| So sánh hai vùng không tạo mảng con | Dùng range overload của cả ba API |
| Mảng đối tượng có quy tắc equality riêng | Truyền cùng Comparator cho overload hỗ trợ Comparator |
| Sắp xếp các mảng theo thứ tự từ điển | Dùng `Arrays.compare` làm Comparator |
| So sánh byte theo miền unsigned | `Arrays.compareUnsigned`; dùng equals/mismatch cho mẫu bit |
| Cần so sánh nội dung mảng lồng nhau | `Arrays.deepEquals` và `Arrays.deepHashCode` |

## 10. Những lỗi thường gặp

- **Cho rằng compare bằng 0 luôn đồng nghĩa với equals true:** điều này có thể sai khi compareTo không nhất quán với equals, ví dụ BigDecimal khác scale.
- **Dùng mismatch không Comparator sau khi equals dùng Comparator:** hai bước có thể áp dụng quy tắc tương đương khác nhau và báo kết quả không nhất quán với mục đích nghiệp vụ.
- **Coi mismatch của range overload là chỉ số tuyệt đối:** kết quả là offset tương đối; cộng với fromIndex để lấy vị trí trong mảng gốc.
- **Coi mismatch bằng độ dài đoạn ngắn hơn là phần tử khác:** trường hợp đó thường có nghĩa một đoạn kết thúc trước, trong khi phần chung giống nhau.
- **Dựa vào giá trị chính xác -1 hoặc 1 của compare:** chỉ kiểm tra dấu âm, 0 hoặc dương.
- **Dùng compare có dấu cho dữ liệu byte unsigned:** dùng compareUnsigned khi cần thứ tự 0 đến 255.
- **Gọi cả equals, compare và mismatch trong mọi trường hợp:** chỉ gọi những phép tính cần cho kết quả hoặc thông báo lỗi.
- **Tạo mảng con để so sánh một vùng:** range overload có thể xử lý trực tiếp hai đoạn và tránh cấp phát bản sao.
- **Bỏ qua hợp đồng null và chỉ số:** xác thực dữ liệu và phạm vi trước khi gọi API nếu chúng đến từ nguồn không tin cậy.

## 11. Tài liệu tham khảo chính thức

- [Arrays — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Arrays.html): hợp đồng của equals, compare, mismatch, compareUnsigned và các overload nhận Comparator/phạm vi.
- [Comparator — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Comparator.html): quy tắc xây dựng thứ tự tùy chỉnh.
- [BigDecimal — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/math/BigDecimal.html): khác biệt giữa equals và compareTo.
- [Comparable — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Comparable.html): hợp đồng của thứ tự tự nhiên và yêu cầu nhất quán với equals.