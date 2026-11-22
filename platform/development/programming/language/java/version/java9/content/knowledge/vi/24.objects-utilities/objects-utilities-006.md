# Kiểm tra điểm đầu và độ dài bằng Objects.checkFromIndexSize

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích hợp đồng của \`Objects.checkFromIndexSize(fromIndex, size, length)\`.
- Phân biệt cách biểu diễn một đoạn bằng điểm đầu và số phần tử với cách dùng hai đầu mút.
- Xử lý đúng đoạn rỗng, đoạn chạm cuối nguồn và các giá trị âm.
- Tránh lỗi tràn số khi tự kiểm tra \`fromIndex + size\`.
- Chọn đúng giữa \`checkIndex\`, \`checkFromToIndex\` và \`checkFromIndexSize\`.

## 1. Vì sao cần checkFromIndexSize?

Một method thường nhận vị trí bắt đầu và số phần tử cần xử lý, ví dụ:

~~~java
int[] copy(int[] source, int offset, int count)
~~~

Ở đây, \`offset\` là điểm bắt đầu và \`count\` là số phần tử cần lấy. Để đoạn nằm hoàn toàn trong nguồn, cần bảo đảm:

- Điểm bắt đầu không âm.
- Số phần tử không âm.
- Đoạn kết thúc không vượt quá độ dài nguồn.

Từ Java 9, \`java.util.Objects.checkFromIndexSize\` cung cấp phép kiểm tra chuẩn cho cách biểu diễn này:

~~~java
int checkedOffset =
        Objects.checkFromIndexSize(offset, count, source.length);
~~~

Nếu range hợp lệ, method trả về chính \`offset\`. Nếu không hợp lệ, method ném \`IndexOutOfBoundsException\`.

Method chỉ xác thực ba giá trị số. Nó không cắt, sao chép hoặc truy cập dữ liệu. Sau khi kiểm tra, caller vẫn phải thực hiện thao tác tương ứng.

## 2. Hợp đồng Java 9 và quy tắc range

Chữ ký được bổ sung trong Java 9:

~~~java
public static int checkFromIndexSize(
        int fromIndex,
        int size,
        int length)
~~~

Các tham số đều là \`int\`:

- \`fromIndex\`: vị trí bắt đầu của đoạn.
- \`size\`: số phần tử cần xử lý.
- \`length\`: độ dài của nguồn.

Range hợp lệ khi thỏa điều kiện toán học:

~~~text
fromIndex >= 0
size >= 0
fromIndex + size <= length
length >= 0
~~~

Có thể hiểu đoạn dữ liệu là:

\`[fromIndex, fromIndex + size)\`

Điểm cuối không được lấy. Khi \`size == 0\`, đoạn là rỗng; vị trí bắt đầu có thể bằng đúng \`length\`.

Ví dụ với nguồn có độ dài 5:

| fromIndex | size | Hợp lệ? | Ý nghĩa |
|---:|---:|---|---|
| 0 | 5 | Có | Lấy toàn bộ nguồn |
| 1 | 3 | Có | Lấy phần tử 1, 2, 3 |
| 2 | 0 | Có | Đoạn rỗng tại vị trí 2 |
| 5 | 0 | Có | Đoạn rỗng ngay sau phần tử cuối |
| -1 | 1 | Không | Điểm đầu âm |
| 1 | -1 | Không | Kích thước âm |
| 4 | 2 | Không | Đoạn vượt quá độ dài |
| 6 | 0 | Không | Điểm đầu nằm ngoài nguồn |

Với range hợp lệ, giá trị trả về là \`fromIndex\`, không phải \`size\` hay điểm cuối. Nếu cần điểm cuối sau khi kiểm tra, có thể tính \`checkedFrom + size\`: phép cộng này an toàn vì range đã được xác nhận nằm trong giới hạn \`length\`.

Lưu ý về phiên bản: overload Java 9 nhận ba giá trị \`int\`. Không truyền trực tiếp \`long\` hoặc ép \`long\` sang \`int\` khi chưa xác nhận giá trị nằm trong miền biểu diễn của \`int\`. Nếu nghiệp vụ cần chỉ số 64-bit, hãy xác thực bằng phép toán \`long\` an toàn riêng trước khi chuyển đổi.

## 3. Vì sao không nên tự kiểm tra bằng phép cộng?

Một cách kiểm tra tưởng như hợp lý là:

~~~java
if (fromIndex < 0
        || size < 0
        || fromIndex + size > length) {
    throw new IndexOutOfBoundsException();
}
~~~

Nhưng \`int\` có giới hạn biểu diễn. Nếu \`fromIndex + size\` vượt quá \`Integer.MAX_VALUE\`, phép cộng có thể tràn và cho ra một số âm hoặc nhỏ hơn giá trị toán học thực. Điều kiện kiểm tra khi đó có thể bỏ lọt range không hợp lệ.

Ví dụ, với \`fromIndex = Integer.MAX_VALUE\` và \`size = 1\`, phép cộng \`int\` bị tràn. Range này không thể nằm trong một nguồn có độ dài tối đa là \`Integer.MAX_VALUE\`.

\`Objects.checkFromIndexSize\` được thiết kế để kiểm tra range mà không dựa vào phép cộng tràn kiểu ngây thơ. Khi đầu vào là điểm đầu và kích thước, hãy dùng method này thay vì tự viết lại phép kiểm tra.

Nếu dữ liệu nghiệp vụ dùng \`long\`, có thể kiểm tra theo dạng phép trừ sau khi xác nhận các giá trị không âm và \`size <= length\`:

~~~java
static long checkLongRange(long from, long size, long length) {
    if (from < 0 || size < 0 || length < 0
            || size > length || from > length - size) {
        throw new IndexOutOfBoundsException("Invalid range");
    }
    return from;
}
~~~

Điều kiện \`size > length\` được kiểm tra trước, nên \`length - size\` không bị tràn xuống dưới khi cả hai đều không âm. Đây là phép kiểm tra riêng cho miền \`long\`; method \`Objects.checkFromIndexSize\` trong Java 9 vẫn nhận \`int\`.

## 4. Dùng trước khi cắt hoặc sao chép mảng

Ví dụ method nhận mảng, điểm đầu và số lượng phần tử:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class RangeCopy {
    public static int[] copy(
            int[] source, int fromIndex, int size) {

        Objects.requireNonNull(source, "source");

        int checkedFrom = Objects.checkFromIndexSize(
                fromIndex, size, source.length);

        int toIndex = checkedFrom + size;
        return Arrays.copyOfRange(source, checkedFrom, toIndex);
    }
}
~~~

Có hai bước kiểm tra riêng:

1. \`Objects.requireNonNull\` xác nhận mảng nguồn không phải \`null\`.
2. \`Objects.checkFromIndexSize\` xác nhận điểm đầu và số phần tử nằm trong giới hạn.

Sau đó, code tính điểm cuối và gọi \`Arrays.copyOfRange\`. Vì range đã được kiểm tra, \`checkedFrom + size\` không vượt quá \`source.length\` và không thể tràn trong một mảng Java hợp lệ.

Điều này cũng làm rõ hợp đồng của method: \`copy(source, 2, 0)\` trả về mảng rỗng, còn \`copy(source, source.length, 0)\` cũng hợp lệ. Nếu size âm hoặc range vượt giới hạn, method thất bại trước khi sao chép.

## 5. Ví dụ hoàn chỉnh có thể chạy

Tạo file **CheckFromIndexSizeDemo.java**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class CheckFromIndexSizeDemo {

    private static int[] copy(
            int[] source, int fromIndex, int size) {

        Objects.requireNonNull(source, "source");

        int checkedFrom = Objects.checkFromIndexSize(
                fromIndex, size, source.length);

        return Arrays.copyOfRange(
                source, checkedFrom, checkedFrom + size);
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

        System.out.println(Arrays.toString(copy(values, 1, 2)));
        System.out.println(Arrays.toString(copy(values, 2, 0)));
        System.out.println(Arrays.toString(copy(values, 4, 0)));

        checkRejected("negative start", () -> copy(values, -1, 1));
        checkRejected("negative size", () -> copy(values, 1, -1));
        checkRejected("range beyond end", () -> copy(values, 3, 2));

        checkRejected("overflow-sized range",
                () -> Objects.checkFromIndexSize(
                        Integer.MAX_VALUE, 1, Integer.MAX_VALUE));
    }
}
~~~

Biên dịch và chạy bằng Java 9:

~~~bash
javac --release 9 -Xlint:all -d out CheckFromIndexSizeDemo.java
java -cp out CheckFromIndexSizeDemo
~~~

Output chính xác:

~~~text
[20, 30]
[]
[]
negative start: rejected
negative size: rejected
range beyond end: rejected
overflow-sized range: rejected
~~~

Ví dụ kiểm tra range rỗng, các giá trị âm, range vượt cuối và trường hợp có nguy cơ tràn số.

## 6. Phân biệt ba method kiểm tra chỉ số của Objects

Java 9 có ba method thường được dùng khi xác thực vị trí hoặc đoạn dữ liệu:

| Method | Dữ liệu đầu vào | Điều kiện |
|---|---|---|
| \`Objects.checkIndex(index, length)\` | Một chỉ số phần tử | \`0 <= index < length\` |
| \`Objects.checkFromToIndex(from, to, length)\` | Điểm đầu và điểm cuối loại trừ | \`0 <= from <= to <= length\` |
| \`Objects.checkFromIndexSize(from, size, length)\` | Điểm đầu và số phần tử | \`from >= 0\`, \`size >= 0\`, đoạn nằm trong length |

Chọn theo cách caller biểu diễn yêu cầu:

~~~java
// Cần truy cập một phần tử.
int checkedIndex = Objects.checkIndex(index, values.length);

// Caller đã có hai đầu mút.
int checkedFrom = Objects.checkFromToIndex(
        from, to, values.length);

// Caller có điểm đầu và số phần tử.
int checkedStart = Objects.checkFromIndexSize(
        from, size, values.length);
~~~

Không cần đổi \`size\` thành \`to\` chỉ để gọi một method khác. Dùng đúng API giúp code thể hiện rõ ý nghĩa tham số và tránh tự thực hiện phép tính dễ sai.

## 7. Áp dụng với array, List và String

Method chỉ nhận ba số nguyên, vì vậy phải truyền đúng độ dài của nguồn:

~~~java
// Array
Objects.checkFromIndexSize(from, size, array.length);

// List
Objects.checkFromIndexSize(from, size, list.size());

// String: length tính theo UTF-16 code unit
Objects.checkFromIndexSize(from, size, text.length());
~~~

Sau khi kiểm tra:

- Với mảng, có thể dùng \`Arrays.copyOfRange(array, from, from + size)\`.
- Với List, có thể dùng \`list.subList(from, from + size)\`.
- Với String, có thể dùng \`text.substring(from, from + size)\`.

Các API truy cập này cũng có kiểm tra giới hạn riêng. Gọi \`checkFromIndexSize\` trước hữu ích khi method cần xác thực range một lần rồi dùng range cho nhiều bước xử lý hoặc muốn công bố hợp đồng đầu vào rõ ràng.

Với \`String\`, \`length()\` đếm UTF-16 code unit, không phải số Unicode code point hoặc số ký tự người dùng nhìn thấy. Range được kiểm tra theo đúng hệ chỉ số mà \`substring\` sử dụng. Nếu yêu cầu nghiệp vụ tính theo code point, cần chuyển đổi vị trí trước khi gọi API.

Luôn truyền đúng length của chính nguồn. Nếu truyền một giá trị length lớn hơn thực tế, phép kiểm tra số học có thể thành công trong khi thao tác truy cập dữ liệu vẫn lỗi.

## 8. Lỗi thường gặp

### Nhầm size với điểm cuối

\`size\` là số phần tử, không phải chỉ số kết thúc. Với \`from = 2\` và \`size = 3\`, đoạn là \`[2, 5)\`.

### Không chấp nhận size bằng 0

Size bằng 0 tạo đoạn rỗng. Nó hợp lệ khi \`0 <= from <= length\`, bao gồm trường hợp \`from == length\`.

### Tự cộng fromIndex và size trước khi kiểm tra

Phép cộng có thể tràn số nguyên. Hãy xác thực bằng \`checkFromIndexSize\` trước; chỉ tính điểm cuối sau khi method đã chấp nhận range.

### Quên kiểm tra null của nguồn

\`checkFromIndexSize\` không nhận tham chiếu nguồn. Nếu cần đọc \`array.length\`, hãy xử lý null trước để có thông báo lỗi rõ ràng.

### Truyền nhầm length

Với array dùng \`array.length\`, với List dùng \`list.size()\`, với String dùng \`string.length()\`. Không dùng capacity hoặc một giới hạn ước lượng.

### Nghĩ rằng method tự cắt dữ liệu

Method chỉ xác thực và trả về điểm đầu. Caller vẫn phải gọi \`copyOfRange\`, \`subList\`, \`substring\` hoặc thao tác phù hợp.

### Khóa test vào exception message

Hợp đồng quan trọng là range hợp lệ hay không và loại exception được ném. Không nên phụ thuộc vào một chuỗi thông báo cụ thể giữa các implementation.

## 9. Checklist

- [ ] Đã hiểu \`fromIndex\` là vị trí bắt đầu và \`size\` là số phần tử.
- [ ] Đã dùng đúng length của nguồn.
- [ ] Đã kiểm tra \`fromIndex >= 0\` và \`size >= 0\`.
- [ ] Đã hiểu range phải nằm hoàn toàn trong nguồn.
- [ ] Đã chấp nhận size bằng 0 tại các vị trí hợp lệ, kể cả cuối nguồn.
- [ ] Đã dùng \`checkFromIndexSize\` thay vì tự cộng trước khi kiểm tra.
- [ ] Đã xử lý null của nguồn riêng.
- [ ] Đã chọn đúng giữa \`checkIndex\`, \`checkFromToIndex\` và \`checkFromIndexSize\`.
- [ ] Đã thực hiện thao tác dữ liệu sau khi xác thực.
- [ ] Đã kiểm tra ví dụ bằng \`javac --release 9\`.

