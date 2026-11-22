# Kiểm tra đoạn bằng Objects.checkFromToIndex

## Mục tiêu

Sau bài học này, bạn có thể:

- Mô tả chính xác hợp đồng của \`Objects.checkFromToIndex(fromIndex, toIndex, length)\`.
- Phân biệt chỉ số bắt đầu, chỉ số kết thúc loại trừ và độ dài vùng dữ liệu.
- Xác định các đoạn hợp lệ, bao gồm đoạn rỗng ở cuối mảng.
- Dùng API Java 9 để xác thực range trước khi cắt hoặc xử lý dữ liệu.
- Chọn đúng giữa \`checkIndex\`, \`checkFromToIndex\` và \`checkFromIndexSize\`.

## 1. \`checkFromToIndex\` giải quyết vấn đề gì?

Khi một method nhận hai vị trí để xử lý một đoạn dữ liệu, nó cần bảo đảm đoạn đó nằm trong giới hạn của nguồn. Ví dụ:

~~~java
int[] copyRange(int[] source, int from, int to)
~~~

Method trên cần xác nhận rằng:

- \`from\` không âm.
- \`to\` không vượt quá độ dài nguồn.
- \`from\` không lớn hơn \`to\`.

Từ Java 9, \`java.util.Objects\` cung cấp \`checkFromToIndex\` để kiểm tra các điều kiện này theo một hợp đồng thống nhất:

~~~java
int checkedFrom = Objects.checkFromToIndex(from, to, source.length);
~~~

Nếu đoạn hợp lệ, method trả về \`from\`. Nếu đoạn không hợp lệ, method ném \`IndexOutOfBoundsException\`.

API này chỉ kiểm tra các giá trị số. Nó không đọc, cắt, sao chép hoặc thay đổi mảng hay collection. Code gọi vẫn phải thực hiện thao tác dữ liệu sau khi kiểm tra.

## 2. Hiểu đúng quy ước đoạn \`[fromIndex, toIndex)\`

Java thường biểu diễn đoạn bằng chỉ số bắt đầu được lấy và chỉ số kết thúc không được lấy:

\`[fromIndex, toIndex)\`

Với một nguồn có \`length = 5\`, các vị trí phần tử hợp lệ là 0 đến 4. Một đoạn hợp lệ phải thỏa:

~~~text
0 <= fromIndex <= toIndex <= length
~~~

Ví dụ:

| Đoạn | Hợp lệ? | Ý nghĩa |
|---|---|---|
| \`[0, 5)\` | Có | Lấy toàn bộ 5 phần tử |
| \`[1, 4)\` | Có | Lấy phần tử ở vị trí 1, 2, 3 |
| \`[2, 2)\` | Có | Đoạn rỗng tại vị trí 2 |
| \`[5, 5)\` | Có | Đoạn rỗng ngay sau phần tử cuối |
| \`[-1, 2)\` | Không | Chỉ số bắt đầu âm |
| \`[3, 2)\` | Không | Điểm kết thúc đứng trước điểm bắt đầu |
| \`[1, 6)\` | Không | Điểm kết thúc vượt quá độ dài |

Điểm dễ nhầm là \`toIndex\` không phải chỉ số phần tử cuối cùng được lấy. Vì đây là đầu mút loại trừ, \`toIndex == length\` là hợp lệ và cho phép lấy phần tử cuối cùng.

Đoạn rỗng cũng hợp lệ nếu vị trí của nó nằm trong khoảng từ 0 đến \`length\`. Do đó, \`[length, length)\` là đoạn rỗng hợp lệ, còn \`[length + 1, length + 1)\` nằm ngoài nguồn.

## 3. Cú pháp, giá trị trả về và ngoại lệ

Chữ ký Java 9:

~~~java
public static int checkFromToIndex(
        int fromIndex,
        int toIndex,
        int length)
~~~

Ý nghĩa tham số:

- \`fromIndex\`: vị trí bắt đầu, được bao gồm trong đoạn.
- \`toIndex\`: vị trí kết thúc, không được bao gồm trong đoạn.
- \`length\`: giới hạn độ dài của nguồn, không phải chỉ số cuối cùng.

Kết quả:

- Nếu \`0 <= fromIndex <= toIndex <= length\`, trả về chính \`fromIndex\`.
- Nếu bất kỳ điều kiện nào không thỏa, ném \`IndexOutOfBoundsException\`.

Giá trị trả về là chỉ số bắt đầu đã được kiểm tra. Nó không phải độ dài đoạn, không phải chỉ số kết thúc và cũng không phải boolean.

Ví dụ:

~~~java
int start = Objects.checkFromToIndex(1, 4, 5);
// start == 1
~~~

Độ dài đoạn vẫn được tính bằng \`toIndex - fromIndex\`, tức 3 trong ví dụ trên.

Không nên phụ thuộc vào nội dung thông báo của exception để kiểm thử. Hợp đồng cần dựa vào loại exception và việc range hợp lệ hay không.

## 4. Ví dụ áp dụng khi cắt mảng

Một method cắt mảng có thể kiểm tra range trước khi gọi API sao chép:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class RangeCopy {
    public static int[] copyRange(
            int[] source, int fromIndex, int toIndex) {

        Objects.requireNonNull(source, "source");

        int checkedFrom = Objects.checkFromToIndex(
                fromIndex, toIndex, source.length);

        return Arrays.copyOfRange(source, checkedFrom, toIndex);
    }
}
~~~

Có hai bước kiểm tra riêng:

1. \`Objects.requireNonNull\` bảo đảm tham chiếu nguồn không phải \`null\`.
2. \`Objects.checkFromToIndex\` bảo đảm hai đầu mút nằm trong giới hạn của mảng.

Sau đó, \`Arrays.copyOfRange\` thực hiện việc sao chép. \`checkFromToIndex\` không thay thế thao tác sao chép.

Việc kiểm tra trước cũng làm rõ hợp đồng của method. Đáng chú ý, \`Arrays.copyOfRange\` có thể đệm giá trị mặc định nếu \`toIndex\` vượt quá độ dài mảng; nếu API của bạn yêu cầu đoạn phải nằm hoàn toàn trong nguồn, \`checkFromToIndex\` ngăn hành vi mở rộng đó.

## 5. Ví dụ hoàn chỉnh có thể chạy

Tạo file **CheckFromToIndexDemo.java**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class CheckFromToIndexDemo {

    private static int[] copyRange(
            int[] source, int fromIndex, int toIndex) {

        Objects.requireNonNull(source, "source");

        int checkedFrom = Objects.checkFromToIndex(
                fromIndex, toIndex, source.length);

        return Arrays.copyOfRange(source, checkedFrom, toIndex);
    }

    private static void checkRejected(
            String label, Runnable operation) {

        try {
            operation.run();
            System.out.println(label + ": unexpected success");
        } catch (IndexOutOfBoundsException ex) {
            System.out.println(label + ": rejected");
        }
    }

    public static void main(String[] args) {
        int[] values = {10, 20, 30, 40};

        System.out.println(Arrays.toString(
                copyRange(values, 1, 3)));

        System.out.println(Arrays.toString(
                copyRange(values, 2, 2)));

        System.out.println(Arrays.toString(
                copyRange(values, 4, 4)));

        checkRejected("negative start",
                () -> copyRange(values, -1, 2));

        checkRejected("reversed range",
                () -> copyRange(values, 3, 2));

        checkRejected("end beyond length",
                () -> copyRange(values, 1, 5));
    }
}
~~~

Biên dịch theo Java 9:

~~~bash
javac --release 9 -Xlint:all -d out CheckFromToIndexDemo.java
java -cp out CheckFromToIndexDemo
~~~

Output chính xác:

~~~text
[20, 30]
[]
[]
negative start: rejected
reversed range: rejected
end beyond length: rejected
~~~

Kết quả cho thấy:

- \`[1, 3)\` lấy hai phần tử ở vị trí 1 và 2.
- \`[2, 2)\` là đoạn rỗng tại vị trí 2.
- \`[4, 4)\` là đoạn rỗng ở cuối mảng, vẫn hợp lệ.
- Chỉ số âm, đoạn đảo ngược và điểm kết thúc vượt giới hạn đều bị từ chối.

## 6. Chọn đúng method kiểm tra chỉ số

Java 9 cung cấp ba method có mục đích gần nhau nhưng nhận cách biểu diễn khác nhau:

| Method | Khi nào dùng? | Điều kiện chính |
|---|---|---|
| \`Objects.checkIndex(index, length)\` | Kiểm tra một phần tử | \`0 <= index < length\` |
| \`Objects.checkFromToIndex(from, to, length)\` | Đã có cả hai đầu mút | \`0 <= from <= to <= length\` |
| \`Objects.checkFromIndexSize(from, size, length)\` | Có vị trí bắt đầu và số phần tử | \`from >= 0\`, \`size >= 0\`, đoạn nằm trong length |

Ví dụ chọn method:

~~~java
int index = Objects.checkIndex(position, values.length);

int from = Objects.checkFromToIndex(
        start, end, values.length);

int checkedStart = Objects.checkFromIndexSize(
        start, count, values.length);
~~~

Dùng \`checkFromToIndex\` khi caller đã cung cấp \`from\` và \`to\`. Dùng \`checkFromIndexSize\` khi caller cung cấp \`from\` và số lượng phần tử cần xử lý.

### 6.1. Vì sao không tự cộng \`from + size\` để kiểm tra?

Một cách kiểm tra dễ viết nhưng không an toàn là:

~~~java
if (from < 0 || size < 0 || from + size > length) {
    throw new IndexOutOfBoundsException();
}
~~~

Phép cộng \`from + size\` có thể tràn số nguyên. Khi tràn, kết quả có thể âm hoặc nhỏ hơn giá trị thực, khiến điều kiện kiểm tra bỏ sót range không hợp lệ.

Nếu đầu vào được biểu diễn bằng vị trí bắt đầu và kích thước, hãy dùng:

~~~java
Objects.checkFromIndexSize(from, size, length);
~~~

API này được thiết kế để kiểm tra dạng range đó mà không dựa vào phép cộng số nguyên có thể tràn.

## 7. Dùng với array, List và String

Method chỉ nhận ba số nguyên, vì vậy caller phải truyền đúng giới hạn của nguồn:

~~~java
// Array
Objects.checkFromToIndex(from, to, array.length);

// List
Objects.checkFromToIndex(from, to, list.size());

// String: chỉ số tính theo UTF-16 code unit
Objects.checkFromToIndex(from, to, text.length());
~~~

Với \`List\`, sau khi kiểm tra có thể dùng \`subList(from, to)\`. Với \`String\`, có thể dùng \`substring(from, to)\`. Các API này vốn có kiểm tra chỉ số riêng; việc gọi \`checkFromToIndex\` trước hữu ích khi method của bạn cần xác thực range rõ ràng hoặc dùng range cho nhiều bước xử lý.

Đối với \`String\`, \`length()\` đếm UTF-16 code unit, không phải số Unicode code point hoặc số ký tự người dùng nhìn thấy. Kiểm tra range vẫn đúng theo quy ước chỉ số mà \`substring\` sử dụng; nếu yêu cầu nghiệp vụ tính theo code point, cần chuyển đổi chỉ số trước khi cắt.

Luôn dùng đúng length của chính nguồn sẽ được xử lý. Nếu truyền nhầm length lớn hơn thực tế, việc kiểm tra số học có thể thành công nhưng thao tác truy cập nguồn vẫn lỗi.

## 8. Lỗi thường gặp

### Nhầm \`toIndex\` là chỉ số phần tử cuối

\`toIndex\` là đầu mút loại trừ. Muốn lấy phần tử ở chỉ số 4, cần có \`toIndex >= 5\`, nếu nguồn đủ dài.

### Từ chối đoạn rỗng

Đoạn \`[x, x)\` hợp lệ khi \`0 <= x <= length\`. Đoạn rỗng hữu ích cho API có thể nhận không phần tử mà không cần coi đó là lỗi.

### Quên kiểm tra null của nguồn

\`checkFromToIndex\` không kiểm tra array hoặc collection. Nếu truy cập \`source.length\` khi \`source\` null, Java ném \`NullPointerException\` trước khi gọi method kiểm tra range.

### Truyền sai length

Với mảng dùng \`array.length\`, với List dùng \`list.size()\`. Không truyền capacity của collection hoặc một giới hạn ước lượng.

### Dùng nhầm method theo dạng tham số

Nếu có \`from\` và \`to\`, dùng \`checkFromToIndex\`. Nếu có \`from\` và \`size\`, dùng \`checkFromIndexSize\`; tránh tự tính \`from + size\`.

### Nghĩ rằng method tự cắt dữ liệu

\`checkFromToIndex\` chỉ xác thực và trả về \`fromIndex\`. Caller vẫn cần gọi \`copyOfRange\`, \`subList\`, \`substring\` hoặc logic xử lý phù hợp.

### Dựa vào exception message

Thông báo có thể thay đổi giữa các implementation hoặc phiên bản. Hãy kiểm tra loại exception và điều kiện hợp lệ, không khóa test vào một chuỗi message cụ thể.

## 9. Checklist

- [ ] Đã xác định \`fromIndex\` được bao gồm và \`toIndex\` bị loại trừ.
- [ ] Đã dùng đúng length của nguồn.
- [ ] Đã hiểu điều kiện \`0 <= from <= to <= length\`.
- [ ] Đã chấp nhận đoạn rỗng tại các vị trí hợp lệ, kể cả \`[length, length)\`.
- [ ] Đã xử lý null riêng nếu nguồn có thể null.
- [ ] Đã chọn \`checkIndex\`, \`checkFromToIndex\` hoặc \`checkFromIndexSize\` theo dạng tham số.
- [ ] Đã thực hiện thao tác cắt hoặc sao chép sau khi kiểm tra.
- [ ] Không dựa vào exception message cụ thể.
- [ ] Đã kiểm tra ví dụ bằng mức release Java phù hợp.

