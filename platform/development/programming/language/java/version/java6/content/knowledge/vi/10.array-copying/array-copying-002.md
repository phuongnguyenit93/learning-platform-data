# Arrays.copyOfRange và khoảng chỉ số đầu gồm, cuối không gồm

## 1. Sao chép một đoạn mảng là làm gì?

Khi chỉ cần một phần dữ liệu, chẳng hạn các phần tử từ vị trí 2 đến trước vị trí 5, ta có thể tạo một mảng mới chứa đoạn đó thay vì tự viết vòng lặp sao chép.

`Arrays.copyOfRange(original, from, to)` nhận mảng nguồn và hai mốc chỉ số. Mảng kết quả bắt đầu lại từ chỉ số 0; mảng nguồn không bị cắt ngắn hay thay đổi cấu trúc.

Điểm quan trọng là tham số thứ ba **là mốc kết thúc**, không phải số phần tử và không phải chỉ số phần tử cuối cùng được lấy:

```text
khoảng yêu cầu: [from, to)
                 ↑      ↑
            có lấy    không lấy

độ dài mảng kết quả = to - from
```

Ví dụ:

```text
chỉ số nguồn:   0    1    2    3    4
giá trị:       10   20   30   40   50
                    └────────┘
                   [1, 4)

kết quả:       20   30   40
chỉ số mới:     0    1    2
```

`copyOfRange(source, 1, 4)` lấy các chỉ số 1, 2, 3. Phần tử chỉ số 4 không thuộc đoạn.

Đây là API có từ Java 6 và vẫn được sử dụng trong Java hiện nay. Các ví dụ trong bài có thể chạy với Java 17 trở lên. Hợp đồng chính thức nằm tại [Arrays.copyOfRange](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Arrays.html#copyOfRange(int%5B%5D,int,int)).

## 2. Vì sao dùng khoảng [from, to)?

Cách biểu diễn đầu gồm, cuối không gồm (inclusive start, exclusive end) giúp thao tác với đoạn liên tiếp dễ tính toán:

- Số phần tử là `to - from`, không cần cộng thêm 1.
- Hai đoạn `[0, split)` và `[split, length)` ghép lại phủ toàn bộ mảng mà không trùng phần tử tại `split`.
- `[k, k)` là đoạn rỗng có độ dài 0.
- Đoạn từ một vị trí đến hết mảng dùng `to = source.length`, dù `source[source.length]` không phải truy cập hợp lệ.

Cần phân biệt **mốc biên** với **chỉ số để truy cập phần tử**. Mốc cuối có thể bằng độ dài mảng vì chính vị trí đó không được lấy.

Nếu bài toán dùng mô tả “từ chỉ số 2 đến chỉ số 4, có lấy cả hai”, cần chuyển thành `copyOfRange(source, 2, 5)`. Không giữ nguyên số 4 làm `to`.

## 3. Điều kiện chỉ số và phần được bù mặc định

Với nguồn khác `null`, các mốc cơ bản phải thỏa:

```text
0 <= from <= original.length
from <= to
```

Điểm dễ bất ngờ: **to được phép lớn hơn original.length**. Khi đó mảng mới vẫn có độ dài `to - from`; phần vượt dữ liệu nguồn được bù bằng giá trị mặc định theo kiểu phần tử.

Ví dụ nguồn `[10, 20, 30, 40, 50]`:

| Lời gọi | Độ dài | Kết quả |
| --- | ---: | --- |
| `copyOfRange(a, 1, 4)` | 3 | `[20, 30, 40]` |
| `copyOfRange(a, 3, 5)` | 2 | `[40, 50]` |
| `copyOfRange(a, 3, 8)` | 5 | `[40, 50, 0, 0, 0]` |
| `copyOfRange(a, 2, 2)` | 0 | `[]` |
| `copyOfRange(a, 5, 5)` | 0 | `[]` |
| `copyOfRange(a, 5, 7)` | 2 | `[0, 0]` |

Trường hợp cuối hợp lệ vì `from` bằng độ dài nguồn. Nó không đọc `a[5]`; toàn bộ kết quả được bù mặc định.

Ngược lại, `copyOfRange(a, 6, 6)` không hợp lệ dù độ dài yêu cầu là 0: mốc bắt đầu đã nằm sau độ dài nguồn.

### Giá trị mặc định phụ thuộc kiểu phần tử

| Kiểu phần tử | Phần bù |
| --- | --- |
| `byte`, `short`, `int`, `long` | Giá trị số 0 tương ứng |
| `float`, `double` | Giá trị 0.0 tương ứng |
| `boolean` | `false` |
| `char` | Ký tự có mã 0 |
| Kiểu tham chiếu như `String`, `Integer`, lớp tự định nghĩa | `null` |

`Integer[]` là mảng tham chiếu nên được bù `null`, không phải đối tượng `Integer` mang giá trị 0. Ký tự có mã 0 cũng khác ký tự `'0'`, có mã 48.

Không xem phần bù là dữ liệu đã tồn tại trong nguồn. Trong xử lý bản tin hoặc đọc khối dữ liệu, việc được bù 0 có thể che giấu lỗi thiếu dữ liệu nếu ứng dụng lẽ ra phải từ chối đoạn vượt biên.

## 4. Ánh xạ vị trí nguồn sang kết quả

Với một vị trí `i` trong mảng kết quả:

```text
vị trí nguồn tương ứng = from + i
```

Nếu vị trí nguồn đó còn nằm trong mảng, giá trị được sao chép. Nếu đã vượt cuối nguồn, vị trí kết quả nhận giá trị mặc định.

Ví dụ `copyOfRange(a, 3, 8)`:

| Chỉ số kết quả | Vị trí nguồn tương ứng | Giá trị |
| ---: | ---: | --- |
| 0 | 3 | 40 |
| 1 | 4 | 50 |
| 2 | 5 | 0 do bù |
| 3 | 6 | 0 do bù |
| 4 | 7 | 0 do bù |

Vì vậy không giữ nguyên chỉ số nguồn khi truy cập kết quả. Phần tử `a[3]` nằm tại `result[0]`, không phải `result[3]`.

## 5. Chương trình đầy đủ: đoạn thường, đoạn rỗng, phần bù và lỗi

Lưu tệp **CopyOfRangeDemo.java**:

```java
import java.util.Arrays;

public class CopyOfRangeDemo {
    private static void showFailure(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + ": no error");
        } catch (RuntimeException e) {
            System.out.println(label + ": "
                    + e.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        int[] source = {10, 20, 30, 40, 50};
        int[] middle = Arrays.copyOfRange(source, 1, 4);

        System.out.println("middle: " + Arrays.toString(middle));
        System.out.println("middle length: " + middle.length);
        System.out.println("suffix: "
                + Arrays.toString(Arrays.copyOfRange(source, 3, 5)));
        System.out.println("padded: "
                + Arrays.toString(Arrays.copyOfRange(source, 3, 8)));
        System.out.println("empty: "
                + Arrays.toString(Arrays.copyOfRange(source, 2, 2)));
        System.out.println("end empty: "
                + Arrays.toString(Arrays.copyOfRange(source, 5, 5)));
        System.out.println("all padding: "
                + Arrays.toString(Arrays.copyOfRange(source, 5, 7)));

        middle[0] = 999;
        System.out.println("changed copy: " + Arrays.toString(middle));
        System.out.println("source: " + Arrays.toString(source));

        String[] words = {"A", "B"};
        System.out.println("reference padding: "
                + Arrays.toString(Arrays.copyOfRange(words, 1, 4)));

        boolean[] flags = {true};
        System.out.println("boolean padding: "
                + Arrays.toString(Arrays.copyOfRange(flags, 0, 3)));

        char[] chars = Arrays.copyOfRange(new char[] {'X'}, 0, 2);
        System.out.println("padded char code: " + (int) chars[1]);

        showFailure("negative from",
                () -> Arrays.copyOfRange(source, -1, 2));
        showFailure("from beyond length",
                () -> Arrays.copyOfRange(source, 6, 6));
        showFailure("reversed range",
                () -> Arrays.copyOfRange(source, 3, 2));
        showFailure("null source",
                () -> Arrays.copyOfRange((int[]) null, 0, 0));
    }
}
```

Biên dịch và chạy:

```shell
javac CopyOfRangeDemo.java
java CopyOfRangeDemo
```

Stdout:

```text
middle: [20, 30, 40]
middle length: 3
suffix: [40, 50]
padded: [40, 50, 0, 0, 0]
empty: []
end empty: []
all padding: [0, 0]
changed copy: [999, 30, 40]
source: [10, 20, 30, 40, 50]
reference padding: [B, null, null]
boolean padding: [true, false, false]
padded char code: 0
negative from: ArrayIndexOutOfBoundsException
from beyond length: ArrayIndexOutOfBoundsException
reversed range: IllegalArgumentException
null source: NullPointerException
```

`middle[0] = 999` chỉ thay đổi phần tử của mảng kết quả. Nguồn vẫn giữ số 20 ở chỉ số 1 vì hai mảng là hai vùng chứa khác nhau.

Hàm `showFailure` chỉ phục vụ quan sát ví dụ. Không nên dùng cách bắt mọi `RuntimeException` rồi tiếp tục như vậy cho xử lý lỗi nghiệp vụ nếu chưa xác định được khả năng phục hồi.

## 6. Hiểu đúng các ngoại lệ

Các tình huống độc lập thường gặp:

| Tình huống | Ngoại lệ |
| --- | --- |
| `from < 0` | `ArrayIndexOutOfBoundsException` |
| `from > original.length` | `ArrayIndexOutOfBoundsException` |
| `from > to` | `IllegalArgumentException` |
| `original == null` | `NullPointerException` |
| Yêu cầu kiểu mảng tham chiếu đích không chứa được một phần tử được sao chép | `ArrayStoreException` |

Nếu một lời gọi đồng thời vi phạm nhiều điều kiện, không thiết kế chương trình dựa vào việc điều kiện nào bị phát hiện trước. Hãy kiểm tra đúng hợp đồng đầu vào của ứng dụng.

Phân biệt rõ hai điều:

- `to > original.length` là trường hợp có thể được bù mặc định.
- `from > original.length` là mốc bắt đầu không hợp lệ.

Không suy từ việc `copyOfRange` cho phép `to` vượt cuối rằng mọi API có tham số `from/to` đều cho phép như vậy. Cùng cách ký hiệu khoảng không có nghĩa cùng chính sách xử lý biên.

## 7. Mảng mới không đồng nghĩa các đối tượng mới

Với mảng kiểu nguyên thủy như `int[]`, phần tử là giá trị nguyên thủy. Với mảng đối tượng, phần tử là tham chiếu. `copyOfRange` sao chép các tham chiếu vào một mảng mới; nó không tự tạo bản sao độc lập của từng đối tượng.

Đây là sao chép nông (shallow copy):

```text
mảng nguồn  ── phần tử 0 ──┐
                          ├── cùng một đối tượng Box
mảng mới    ── phần tử 0 ──┘
```

Hai thao tác sau khác nhau:

- Thay `copy[0]` bằng một đối tượng khác chỉ thay phần tử trong mảng mới.
- Thay `copy[0].value` làm thay đổi đối tượng đang được cả hai mảng tham chiếu.

Với mảng hai chiều, mỗi phần tử của mảng ngoài cũng là một tham chiếu tới mảng con. Sao chép một đoạn của mảng ngoài không tự sao chép từng hàng bên trong.

### Kiểu khai báo và kiểu mảng thực tế

Với phiên bản ba tham số dành cho mảng tham chiếu, kiểu mảng thực tế của kết quả giống nguồn. Nếu biến có kiểu `Number[]` nhưng đang trỏ tới một `Integer[]`, bản sao vẫn là `Integer[]`.

Phiên bản có tham số thứ tư cho phép yêu cầu kiểu mảng kết quả, chẳng hạn `Number[].class`. Nó vẫn sao chép tham chiếu và vẫn yêu cầu phần tử nguồn tương thích với kiểu đích. Xem [copyOfRange cho mảng tham chiếu](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Arrays.html#copyOfRange(U%5B%5D,int,int,java.lang.Class)).

## 8. Chương trình đầy đủ: tham chiếu dùng chung và kiểu thực tế

Lưu tệp **ReferenceRangeDemo.java**:

```java
import java.util.Arrays;

public class ReferenceRangeDemo {
    static class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        Box[] original = {new Box(10), new Box(20)};
        Box[] copy = Arrays.copyOfRange(original, 0, 1);

        System.out.println("different arrays: " + (original != copy));
        System.out.println("same first object: "
                + (original[0] == copy[0]));

        copy[0].value = 99;
        System.out.println("original object value: " + original[0].value);

        copy[0] = new Box(7);
        System.out.println("original after replacement: "
                + original[0].value);
        System.out.println("copy after replacement: " + copy[0].value);

        int[][] matrix = {{1, 2}, {3, 4}};
        int[][] rows = Arrays.copyOfRange(matrix, 0, 1);
        rows[0][0] = 8;
        System.out.println("original matrix value: " + matrix[0][0]);

        Number[] numbers = new Integer[] {1, 2, 3};
        Number[] sameType = Arrays.copyOfRange(numbers, 0, 2);
        System.out.println("default runtime type: "
                + sameType.getClass().getTypeName());

        try {
            sameType[0] = 1.5;
        } catch (ArrayStoreException e) {
            System.out.println("storing Double: "
                    + e.getClass().getSimpleName());
        }

        Number[] wider = Arrays.copyOfRange(
                numbers, 0, 2, Number[].class);
        wider[0] = 1.5;
        System.out.println("requested runtime type: "
                + wider.getClass().getTypeName());
        System.out.println("wider contents: " + Arrays.toString(wider));

        Number[] mixed = {1, 2.5};
        try {
            Arrays.copyOfRange(mixed, 0, 2, Integer[].class);
        } catch (ArrayStoreException e) {
            System.out.println("incompatible requested type: "
                    + e.getClass().getSimpleName());
        }
    }
}
```

Chạy:

```shell
javac ReferenceRangeDemo.java
java ReferenceRangeDemo
```

Stdout:

```text
different arrays: true
same first object: true
original object value: 99
original after replacement: 99
copy after replacement: 7
original matrix value: 8
default runtime type: java.lang.Integer[]
storing Double: ArrayStoreException
requested runtime type: java.lang.Number[]
wider contents: [1.5, 2]
incompatible requested type: ArrayStoreException
```

Hai trường hợp `ArrayStoreException` có nguyên nhân khác thời điểm:

- `sameType` được tạo thành công nhưng việc gán một `Double` vào `Integer[]` xảy ra lỗi sau đó.
- Bản sao từ `mixed` sang `Integer[]` thất bại ngay trong thao tác sao chép vì phần tử `2.5` không chứa được trong mảng đích.

Yêu cầu `Number[].class` tạo vùng chứa rộng hơn; nó không biến các phần tử `Integer` hiện có thành các đối tượng kiểu khác.

## 9. Khi nghiệp vụ yêu cầu cắt đoạn nghiêm ngặt

Nếu đang tách một gói dữ liệu và yêu cầu mọi phần tử của đoạn phải có trong nguồn, phần bù mặc định có thể là điều không mong muốn. Khi đó nên kiểm tra thêm `to <= source.length` trước khi sao chép.

Ví dụ một phương thức tiện ích, đặt bên trong lớp của ứng dụng:

```java
import java.util.Arrays;
import java.util.Objects;

// Phương thức thành viên, không phải chương trình độc lập.
static int[] strictSlice(int[] source, int from, int to) {
    Objects.requireNonNull(source, "source");
    Objects.checkFromToIndex(from, to, source.length);
    return Arrays.copyOfRange(source, from, to);
}
```

[`Objects.checkFromToIndex`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Objects.html#checkFromToIndex(int,int,int)) kiểm tra khoảng hoàn toàn nằm trong giới hạn. Vì vậy `strictSlice(source, 3, 8)` sẽ từ chối với nguồn dài 5, trong khi `Arrays.copyOfRange(source, 3, 8)` sẽ tạo phần bù. Đây là chính sách đầu vào bổ sung của phương thức tiện ích.

Với dữ liệu do bên ngoài cung cấp, còn cần giới hạn kích thước kết quả hợp lý. Một mốc `to` rất lớn có thể yêu cầu cấp phát một mảng rất lớn; việc cho phép bù mặc định không biến thao tác thành không tốn bộ nhớ.

## 10. Chọn đúng thao tác và tránh lỗi lệch một vị trí

| Nhu cầu | Thao tác phù hợp |
| --- | --- |
| Tạo mảng mới từ một đoạn bắt đầu tại `from` | `Arrays.copyOfRange` |
| Tạo mảng mới từ đầu nguồn với độ dài mong muốn | `Arrays.copyOf` |
| Ghi một đoạn vào mảng đích đã có | `System.arraycopy` |

`copyOfRange` tự tạo mảng kết quả. Không truyền mảng đích hay vị trí đích như với `System.arraycopy`.

Các lỗi thường gặp:

- Dùng `to = source.length - 1` khi muốn lấy tới cuối, làm bỏ phần tử cuối.
- Dùng `to = count` khi yêu cầu là “lấy count phần tử từ from”. Mốc đúng là `from + count`, sau khi đã kiểm tra số học và giới hạn.
- Cho rằng `from == to` luôn hợp lệ, dù `from` đã nằm ngoài phạm vi cho phép.
- Cho rằng `to` vượt biên luôn gây ngoại lệ, rồi vô tình chấp nhận dữ liệu thiếu vì được bù 0 hoặc `null`.
- Nhầm mảng kết quả với một khung nhìn chia sẻ các phần tử mảng nguồn. Vùng chứa là mới; đối tượng được tham chiếu có thể vẫn dùng chung.
- Sao chép liên tục các đoạn lớn trong vòng lặp dù chỉ cần đọc chúng. Mỗi lời gọi tạo vùng chứa mới; nếu không cần mảng độc lập, có thể truyền nguồn cùng các mốc để xử lý trực tiếp theo thiết kế của ứng dụng.

Để tính `from + count` an toàn với số liệu ngoài ứng dụng, có thể kiểm tra trước `count >= 0`, `0 <= from <= source.length` và `count <= source.length - from` khi yêu cầu không bù. Cách kiểm tra này tránh cộng trước rồi mới phát hiện tràn số.

## 11. Tự thực hành

Với `int[] a = {4, 8, 12, 16};`, hãy dự đoán trước khi chạy:

| Lời gọi | Câu hỏi |
| --- | --- |
| `copyOfRange(a, 1, 3)` | Những chỉ số nào được lấy? |
| `copyOfRange(a, 2, 6)` | Bao nhiêu phần tử thật và bao nhiêu phần tử bù? |
| `copyOfRange(a, 4, 4)` | Vì sao không truy cập `a[4]`? |
| `copyOfRange(a, 4, 6)` | Toàn bộ kết quả có nguồn gốc từ đâu? |
| `copyOfRange(a, 5, 5)` | Đoạn dài 0 có đủ để làm lời gọi hợp lệ không? |

Đáp án:

1. `[8, 12]`, lấy chỉ số 1 và 2.
2. `[12, 16, 0, 0]`, có hai phần tử nguồn và hai phần tử bù.
3. `[]`, vì khoảng rỗng và mốc bắt đầu bằng độ dài nguồn được cho phép.
4. `[0, 0]`, cả hai vị trí đều là phần bù.
5. Ném `ArrayIndexOutOfBoundsException`, vì mốc bắt đầu vượt độ dài nguồn.

Sau đó thử cùng yêu cầu với `Integer[]` để quan sát phần bù `null`, và với mảng chứa đối tượng có thể thay đổi để phân biệt sao chép vùng chứa với sao chép đối tượng.
