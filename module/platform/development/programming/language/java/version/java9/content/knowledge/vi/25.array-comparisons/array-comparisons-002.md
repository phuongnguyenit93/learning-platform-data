# So sánh mảng số nguyên không dấu bằng Arrays.compareUnsigned

## Mục tiêu

Java 9 bổ sung các phương thức `Arrays.compareUnsigned(...)` để so sánh hai mảng số nguyên theo thứ tự từ điển, trong đó mỗi phần tử được diễn giải như một giá trị **không dấu (unsigned)**.

API này hữu ích khi xử lý byte của giao thức mạng, dữ liệu nhị phân, khóa dạng byte, bộ đếm hoặc các giá trị được lưu dưới dạng bit nhưng cần so sánh theo miền không dấu. Nó giúp tránh việc tự chuyển từng phần tử sang kiểu rộng hơn rồi viết vòng lặp so sánh.

Cần nhớ hai điều: phương thức so sánh từng phần tử theo thứ tự từ điển, không coi toàn bộ mảng là một số nguyên duy nhất; và nó không thay đổi kiểu dữ liệu hay bit bên trong mảng.

## 1. Signed và unsigned trong Java

Các kiểu số nguyên primitive `byte`, `short`, `int` và `long` được Java diễn giải theo dạng có dấu khi dùng các phép so sánh thông thường.

| Kiểu | Miền có dấu | Miền không dấu tương ứng |
|---|---:|---:|
| `byte` | -128 đến 127 | 0 đến 255 |
| `short` | -32.768 đến 32.767 | 0 đến 65.535 |
| `int` | -2³¹ đến 2³¹ - 1 | 0 đến 2³² - 1 |
| `long` | -2⁶³ đến 2⁶³ - 1 | 0 đến 2⁶⁴ - 1 |

Java không có kiểu primitive `uint` hoặc `ulong`. Các phương thức unsigned diễn giải cùng một mẫu bit theo miền không dấu mà không cần thay đổi cách lưu trữ.

Ví dụ, một byte có mẫu bit `11111111` được biểu diễn là `-1` khi đọc theo kiểu `byte`, nhưng giá trị không dấu tương ứng là `255`. Tương tự, mẫu bit toàn số 1 của một `int` có giá trị có dấu là `-1`, còn cách diễn giải không dấu là `4294967295`.

## 2. Arrays.compareUnsigned là gì?

Lớp `java.util.Arrays` cung cấp các overload để so sánh hai mảng:

~~~java
Arrays.compareUnsigned(byte[] a, byte[] b)
Arrays.compareUnsigned(short[] a, short[] b)
Arrays.compareUnsigned(int[] a, int[] b)
Arrays.compareUnsigned(long[] a, long[] b)
~~~

Các overload này có từ Java 9. Chúng so sánh các phần tử theo thứ tự từ điển (lexicographical order), giống cách so sánh chuỗi ký tự nhưng dùng giá trị số không dấu của từng phần tử.

Quy tắc so sánh:

1. So sánh phần tử thứ nhất của hai mảng theo unsigned.
2. Nếu hai phần tử bằng nhau, tiếp tục so sánh phần tử kế tiếp.
3. Phần tử khác nhau đầu tiên quyết định kết quả.
4. Nếu toàn bộ phần tử trong phần chung đều bằng nhau, mảng ngắn hơn được xem là nhỏ hơn.
5. Nếu hai mảng có cùng độ dài và mọi phần tử đều bằng nhau, kết quả bằng 0.

Giá trị trả về là một số nguyên âm, bằng 0 hoặc dương tương ứng với mảng thứ nhất nhỏ hơn, bằng hoặc lớn hơn mảng thứ hai. Chỉ nên dựa vào dấu của kết quả; không phụ thuộc vào độ lớn chính xác của số được trả về.

Ví dụ:

~~~java
byte[] first = {(byte) 0xFF};
byte[] second = {0x01};

int result = Arrays.compareUnsigned(first, second);
~~~

Theo cách diễn giải không dấu, phần tử đầu tiên là 255 và phần tử thứ hai là 1. Vì vậy kết quả dương, dù giá trị `byte` đầu tiên khi in theo kiểu có dấu là `-1`.

## 3. So sánh từng loại mảng

### byte[]

Đây là trường hợp thường gặp khi xử lý dữ liệu nhị phân. `byte` là kiểu có dấu, vì vậy byte có bit cao nhất bằng 1 thường có giá trị âm nếu in trực tiếp. `compareUnsigned` diễn giải byte trong miền 0 đến 255.

~~~java
byte[] a = {(byte) 0x80};
byte[] b = {0x7F};

System.out.println(Integer.signum(Arrays.compare(a, b)));
System.out.println(Integer.signum(Arrays.compareUnsigned(a, b)));
~~~

Kết quả:

~~~text
-1
1
~~~

Theo signed, -128 nhỏ hơn 127. Theo unsigned, 128 lớn hơn 127.

### short[]

Với `short[]`, mỗi phần tử được diễn giải trong miền 0 đến 65.535:

~~~java
short[] a = {(short) 0xFFFF};
short[] b = {1};

int result = Arrays.compareUnsigned(a, b);
~~~

Phần tử đầu tiên có giá trị signed là -1, nhưng giá trị unsigned là 65.535. Do đó mảng `a` lớn hơn mảng `b` theo unsigned.

### int[]

Với `int[]`, mỗi phần tử được diễn giải trong miền 0 đến 2³² - 1:

~~~java
int[] a = {0xFFFF_FFFF};
int[] b = {1};

System.out.println(Integer.signum(Arrays.compare(a, b)));
System.out.println(Integer.signum(Arrays.compareUnsigned(a, b)));
~~~

Kết quả:

~~~text
-1
1
~~~

Mẫu bit `0xFFFF_FFFF` có giá trị signed là -1 và unsigned là 4.294.967.295. Phương thức unsigned so sánh theo giá trị thứ hai.

### long[]

Với `long[]`, mỗi phần tử được diễn giải trong miền 0 đến 2⁶⁴ - 1. Một giá trị unsigned lớn hơn `Long.MAX_VALUE` vẫn được lưu bằng cùng 64 bit trong kiểu `long`, vì vậy khi hiển thị cần dùng `Long.toUnsignedString` nếu muốn thấy giá trị không dấu.

~~~java
long[] a = {0xFFFF_FFFF_FFFF_FFFFL};
long[] b = {1L};

System.out.println(Long.toUnsignedString(a[0]));
System.out.println(Integer.signum(Arrays.compareUnsigned(a, b)));
~~~

Kết quả:

~~~text
18446744073709551615
1
~~~

## 4. So sánh từ điển và quy tắc độ dài

`Arrays.compareUnsigned` không so sánh tổng giá trị của tất cả phần tử. Nó so sánh tuần tự từ trái sang phải, phần tử khác nhau đầu tiên quyết định thứ tự.

Ví dụ:

~~~java
int[] a = {1, 9, 100};
int[] b = {1, 10, 0};

System.out.println(Integer.signum(Arrays.compareUnsigned(a, b)));
~~~

Kết quả:

~~~text
-1
~~~

Phần tử đầu tiên bằng nhau. Ở vị trí thứ hai, 9 nhỏ hơn 10, nên mảng `a` nhỏ hơn; phần tử thứ ba không còn ảnh hưởng.

Nếu một mảng là tiền tố của mảng kia, mảng ngắn hơn nhỏ hơn:

~~~java
int[] prefix = {1, 2};
int[] longer = {1, 2, 0};

System.out.println(Integer.signum(
        Arrays.compareUnsigned(prefix, longer)));
~~~

Kết quả:

~~~text
-1
~~~

Quy tắc này cũng áp dụng cho các đoạn mảng khi dùng overload có chỉ số bắt đầu và kết thúc.

### Khi nào thứ tự từ điển tương ứng với thứ tự số?

Với các byte biểu diễn một số nguyên không dấu theo thứ tự byte big-endian và có cùng độ dài, so sánh từ điển unsigned cho cùng thứ tự với so sánh giá trị số. Byte quan trọng nhất nằm trước nên phần tử khác nhau đầu tiên quyết định giá trị lớn nhỏ.

Không nên mặc định điều đó cho mọi định dạng dữ liệu. Với biểu diễn little-endian, thứ tự byte khác nhau; với dữ liệu có quy tắc mã hóa riêng hoặc độ dài không cố định, cần kiểm tra định dạng trước khi dùng kết quả so sánh như thứ tự số học.

## 5. So sánh toàn bộ mảng và so sánh một đoạn

Java 9 cũng cung cấp overload để so sánh hai đoạn mảng mà không cần tạo mảng con:

~~~java
Arrays.compareUnsigned(
        a, aFromIndex, aToIndex,
        b, bFromIndex, bToIndex)
~~~

Các chỉ số dùng quy ước nửa mở: bắt đầu tại `fromIndex` và kết thúc ngay trước `toIndex`. Vì vậy số phần tử được so sánh là `toIndex - fromIndex`.

Ví dụ:

~~~java
int[] left = {99, 0xFFFF_FFFF, 7, 99};
int[] right = {0, 1, 7, 0};

int result = Arrays.compareUnsigned(
        left, 1, 3,
        right, 1, 3
);

System.out.println(Integer.signum(result));
~~~

Kết quả:

~~~text
1
~~~

Chỉ hai đoạn `left[1..3)` và `right[1..3)` được so sánh. Phần tử đầu tiên của đoạn trái có mẫu bit `0xFFFF_FFFF`, tương ứng unsigned 4.294.967.295, lớn hơn 1 ở đoạn phải.

Các overload theo đoạn cũng có cho `byte[]`, `short[]` và `long[]`.

Khi chỉ cần so sánh một vùng dữ liệu, overload theo đoạn giúp tránh tạo bản sao bằng `Arrays.copyOfRange`. Dữ liệu gốc không bị thay đổi.

## 6. Phân biệt Arrays.compare và Arrays.compareUnsigned

Hai API đều so sánh mảng theo thứ tự từ điển, nhưng khác cách diễn giải từng phần tử:

- `Arrays.compare(...)` so sánh theo giá trị có dấu thông thường của kiểu primitive.
- `Arrays.compareUnsigned(...)` so sánh theo giá trị không dấu của các kiểu số nguyên được hỗ trợ.

Ví dụ:

~~~java
int[] highBit = {0x8000_0000};
int[] positive = {1};

System.out.println(Integer.signum(
        Arrays.compare(highBit, positive)));

System.out.println(Integer.signum(
        Arrays.compareUnsigned(highBit, positive)));
~~~

Kết quả:

~~~text
-1
1
~~~

Mẫu bit `0x8000_0000` là -2.147.483.648 khi diễn giải signed, nhưng là 2.147.483.648 khi diễn giải unsigned.

Không nhầm hai API này với `Arrays.equals`: equals chỉ kiểm tra hai mảng có nội dung bằng nhau hay không, còn compare trả về thứ tự tương đối giữa hai mảng.

## 7. Liên hệ với các phương thức compareUnsigned trên từng giá trị

Java còn có các phương thức so sánh unsigned cho từng giá trị nguyên, ví dụ:

~~~java
Integer.compareUnsigned(left, right)
Long.compareUnsigned(left, right)
~~~

Các phương thức này so sánh hai giá trị đơn lẻ. `Arrays.compareUnsigned` áp dụng quy tắc tương tự cho từng cặp phần tử trong mảng và dừng tại phần tử khác nhau đầu tiên.

Có thể hình dung:

- So sánh một cặp `int`: dùng `Integer.compareUnsigned`.
- So sánh một cặp `long`: dùng `Long.compareUnsigned`.
- So sánh hai mảng `int[]` hoặc `long[]`: dùng `Arrays.compareUnsigned`.

Không cần tự viết vòng lặp chỉ để thực hiện phép so sánh từ điển unsigned trên các kiểu mảng được hỗ trợ.

## 8. Sắp xếp các mảng theo thứ tự unsigned

Vì `Arrays.compareUnsigned` trả về thứ tự từ điển, có thể dùng nó làm Comparator để sắp xếp một mảng chứa các mảng byte:

~~~java
byte[][] keys = {
        {(byte) 0xFF},
        {0x01},
        {(byte) 0x80}
};

Arrays.sort(keys, Arrays::compareUnsigned);
~~~

Thứ tự sau khi sắp xếp là byte unsigned 1, 128, 255. Khi dùng `Arrays.toString` để in từng mảng, byte vẫn hiển thị theo kiểu signed là 1, -128, -1; điều đó không có nghĩa thứ tự unsigned bị sai.

Cách sắp xếp này hữu ích khi cần thứ tự từ điển cho các khóa nhị phân. Hãy xác định rõ định dạng byte và thứ tự mong muốn trước khi dùng nó làm thứ tự nghiệp vụ.

## 9. Ví dụ hoàn chỉnh có thể chạy

Tệp `CompareUnsignedDemo.java`:

~~~java
import java.util.Arrays;

public class CompareUnsignedDemo {
    public static void main(String[] args) {
        byte[] bytesHigh = {(byte) 0xFF};
        byte[] bytesLow = {0x01};

        short[] shortsHigh = {(short) 0xFFFF};
        short[] shortsLow = {0x0001};

        int[] intsHigh = {0xFFFF_FFFF};
        int[] intsLow = {0x0000_0001};

        long[] longsHigh = {0xFFFF_FFFF_FFFF_FFFFL};
        long[] longsLow = {0x0000_0000_0000_0001L};

        System.out.println("byte unsigned: "
                + Integer.signum(Arrays.compareUnsigned(bytesHigh, bytesLow)));
        System.out.println("short unsigned: "
                + Integer.signum(Arrays.compareUnsigned(shortsHigh, shortsLow)));
        System.out.println("int unsigned: "
                + Integer.signum(Arrays.compareUnsigned(intsHigh, intsLow)));
        System.out.println("long unsigned: "
                + Integer.signum(Arrays.compareUnsigned(longsHigh, longsLow)));

        System.out.println("int signed: "
                + Integer.signum(Arrays.compare(intsHigh, intsLow)));
        System.out.println("int unsigned: "
                + Integer.signum(Arrays.compareUnsigned(intsHigh, intsLow)));

        int[] prefix = {1, 2};
        int[] longer = {1, 2, 0};
        System.out.println("shorter prefix: "
                + Integer.signum(Arrays.compareUnsigned(prefix, longer)));

        int[] rangeLeft = {99, 0xFFFF_FFFF, 7, 99};
        int[] rangeRight = {0, 1, 7, 0};
        System.out.println("unsigned range: "
                + Integer.signum(Arrays.compareUnsigned(
                        rangeLeft, 1, 3, rangeRight, 1, 3)));
    }
}
~~~

Biên dịch và chạy bằng JDK 9 trở lên:

~~~bash
javac --release 9 -Xlint:all CompareUnsignedDemo.java
java CompareUnsignedDemo
~~~

Kết quả chuẩn:

~~~text
byte unsigned: 1
short unsigned: 1
int unsigned: 1
long unsigned: 1
int signed: -1
int unsigned: 1
shorter prefix: -1
unsigned range: 1
~~~

Chương trình kiểm tra bốn overload cho các kiểu mảng số nguyên, so sánh signed và unsigned trên cùng một dữ liệu, quy tắc mảng tiền tố và overload so sánh hai đoạn.

## 10. Ngoại lệ và lỗi thường gặp

| Tình huống | Hành vi hoặc nguyên nhân | Cách xử lý |
|---|---|---|
| Một trong hai mảng là null | Phát sinh NullPointerException | Kiểm tra hợp đồng đầu vào hoặc xử lý null trước khi so sánh |
| Chỉ số đoạn âm hoặc vượt độ dài mảng | Phát sinh lỗi chỉ số mảng | Xác minh fromIndex và toIndex nằm trong giới hạn |
| fromIndex lớn hơn toIndex | Phát sinh IllegalArgumentException | Bảo đảm đoạn có thứ tự chỉ số hợp lệ |
| Dùng Arrays.compare khi cần unsigned | Các phần tử âm được xem là nhỏ hơn số dương | Dùng Arrays.compareUnsigned |
| Nghĩ kết quả trả về luôn là -1, 0 hoặc 1 | API chỉ cam kết âm, 0 hoặc dương | Dùng Integer.signum nếu cần chuẩn hóa dấu |
| Dùng == để so sánh nội dung hai mảng | == kiểm tra hai biến có tham chiếu cùng một mảng hay không | Dùng Arrays.compareUnsigned hoặc Arrays.equals theo mục đích |
| Coi toàn bộ byte[] là một số nguyên | API so sánh từ điển từng byte | Xác định định dạng số và thứ tự byte trước khi diễn giải kết quả số học |
| In byte âm rồi kết luận phép so sánh sai | byte được in theo kiểu signed | Dùng Byte.toUnsignedInt hoặc định dạng hex khi cần xem giá trị unsigned |

## 11. Checklist khi áp dụng

- Xác định dữ liệu cần so sánh theo signed hay unsigned.
- Chọn đúng overload cho `byte[]`, `short[]`, `int[]` hoặc `long[]`.
- Nhớ rằng phần tử khác nhau đầu tiên quyết định thứ tự.
- Nếu phần chung bằng nhau, mảng ngắn hơn được xem là nhỏ hơn.
- Dùng overload theo đoạn khi chỉ cần so sánh một vùng.
- Không phụ thuộc vào độ lớn chính xác của giá trị trả về; chỉ xét âm, 0 hoặc dương.
- Không nhầm thứ tự từ điển với giá trị số học của toàn bộ mảng.
- Xử lý null và chỉ số đoạn theo hợp đồng đầu vào.
- Kiểm tra định dạng big-endian/little-endian nếu mảng biểu diễn số nhị phân.
- Nhớ rằng `Arrays.compareUnsigned` là API hiện hành từ Java 9.

`Arrays.compareUnsigned` cung cấp phép so sánh từ điển unsigned nhất quán cho các mảng số nguyên. Khi hiểu rõ signedness, thứ tự phần tử và quy tắc độ dài, có thể dùng API này để so sánh dữ liệu nhị phân và các giá trị nguyên không dấu một cách rõ ràng, an toàn và dễ kiểm thử.