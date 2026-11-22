# So sánh mục đích với System.arraycopy

## 1. Cùng sao chép phần tử, nhưng giải quyết nhu cầu khác nhau

Khi làm việc với mảng, ta thường gặp hai nhu cầu:

- Tạo một mảng mới chứa toàn bộ hoặc một đoạn dữ liệu nguồn.
- Ghi một đoạn dữ liệu vào một mảng đích đã tồn tại, tại một vị trí cụ thể.

`Arrays.copyOf` và `Arrays.copyOfRange` thuận tiện cho nhu cầu thứ nhất. `System.arraycopy` trực tiếp diễn tả nhu cầu thứ hai.

Đừng chọn chỉ vì tên phương thức có chữ “copy”. Trước hết hãy xác định **ai tạo vùng chứa đích, dữ liệu bắt đầu ở đâu trong đích và ứng dụng muốn giữ lại những phần nào của đích**.

Ví dụ:

```text
tạo mảng mới:
nguồn [A B C D] → kết quả mới [B C]

ghi vào đích đã có:
nguồn [A B C D]
          └─┘
đích trước [x x x x x x]
đích sau   [x x B C x x]
```

Hai trường hợp đều chuyển các phần tử B và C, nhưng trường hợp thứ hai phải giữ những ô `x` nằm ngoài vùng ghi. Đó là lý do tham số vị trí đích của `System.arraycopy` có ý nghĩa riêng.

Các API này vẫn được sử dụng trong Java hiện nay. Bài dùng ví dụ chạy với Java 17 trở lên, không dựa vào hành vi lỗi thời.

## 2. Bảng chọn theo mục đích

| Đặc điểm | Arrays.copyOf | Arrays.copyOfRange | System.arraycopy |
| --- | --- | --- | --- |
| Tạo mảng kết quả mới | Có | Có | Không, bên gọi cung cấp đích |
| Kết quả trả về | Mảng mới | Mảng mới | `void` |
| Điểm bắt đầu ở nguồn | 0 | `from` | `srcPos` |
| Điểm bắt đầu ở đích | 0 | 0 | `destPos` |
| Cách mô tả kích thước | `newLength`: độ dài kết quả | `to - from`: độ dài kết quả | `length`: số phần tử cần chuyển |
| Dùng khi cần giữ phần còn lại của đích có sẵn | Không phải vai trò trực tiếp | Không phải vai trò trực tiếp | Phù hợp |
| Dịch phần tử trong cùng một mảng | Không trực tiếp | Không trực tiếp | Có, kể cả vùng chồng lấp |

Ví dụ chọn nhanh:

- Muốn bản sao độc lập về vùng chứa: `Arrays.copyOf(source, source.length)`.
- Muốn lấy đoạn từ chỉ số 2 đến trước chỉ số 5: `Arrays.copyOfRange(source, 2, 5)`.
- Muốn đặt ba phần tử đó vào đích bắt đầu tại chỉ số 4: `System.arraycopy(source, 2, target, 4, 3)`.

Hợp đồng chi tiết: [Arrays.copyOf và copyOfRange](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Arrays.html), [System.arraycopy](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html#arraycopy(java.lang.Object,int,java.lang.Object,int,int)).

## 3. Đọc đúng năm tham số của System.arraycopy

Chữ ký phương thức:

```java
public static void arraycopy(
        Object src, int srcPos,
        Object dest, int destPos,
        int length)
```

Đây là chữ ký API, không phải phần khai báo cần chép vào chương trình.

| Tham số | Vai trò |
| --- | --- |
| `src` | Đối tượng mảng nguồn |
| `srcPos` | Chỉ số bắt đầu lấy trong nguồn |
| `dest` | Đối tượng mảng đích đã có |
| `destPos` | Chỉ số bắt đầu ghi trong đích |
| `length` | Số phần tử cần sao chép |

Với mỗi `i` từ 0 đến `length - 1`, vị trí tương ứng là:

```text
src[srcPos + i] → dest[destPos + i]
```

Ví dụ:

```java
// Đoạn minh họa; hai mảng đã được khởi tạo.
System.arraycopy(source, 1, target, 2, 2);
```

Lệnh này lấy hai phần tử tại chỉ số nguồn 1 và 2, rồi ghi vào chỉ số đích 2 và 3. Số 2 cuối cùng là **số lượng**, không phải mốc kết thúc của đoạn nguồn hoặc đoạn đích.

Hai tham số mảng có kiểu khai báo `Object` để một chữ ký có thể nhận nhiều loại mảng. Điều đó không có nghĩa mọi đối tượng `Object` đều là đối số hợp lệ: chúng vẫn phải là mảng có kiểu tương thích khi chạy.

## 4. Chương trình đầy đủ: mảng mới và mảng đích có sẵn

Lưu tệp **ArrayCopyPurposeDemo.java**:

```java
import java.util.Arrays;

public class ArrayCopyPurposeDemo {
    public static void main(String[] args) {
        int[] source = {2, 4, 6, 8};

        int[] expanded = Arrays.copyOf(source, 6);
        int[] slice = Arrays.copyOfRange(source, 1, 3);

        int[] target = new int[6];
        Arrays.fill(target, -1);
        int[] targetAlias = target;
        System.arraycopy(source, 1, target, 2, 2);

        System.out.println("expanded: " + Arrays.toString(expanded));
        System.out.println("slice: " + Arrays.toString(slice));
        System.out.println("target: " + Arrays.toString(target));
        System.out.println("same target object: "
                + (targetAlias == target));
        System.out.println("alias sees write: " + targetAlias[2]);
        System.out.println("source: " + Arrays.toString(source));

        expanded[0] = 100;
        System.out.println("source after new copy edit: " + source[0]);

        int[] right = {1, 2, 3, 4, 5};
        System.arraycopy(right, 0, right, 1, 4);
        System.out.println("shift right: " + Arrays.toString(right));

        int[] left = {1, 2, 3, 4, 5};
        System.arraycopy(left, 1, left, 0, 4);
        System.out.println("shift left: " + Arrays.toString(left));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac ArrayCopyPurposeDemo.java
java ArrayCopyPurposeDemo
```

Stdout:

```text
expanded: [2, 4, 6, 8, 0, 0]
slice: [4, 6]
target: [-1, -1, 4, 6, -1, -1]
same target object: true
alias sees write: 4
source: [2, 4, 6, 8]
source after new copy edit: 2
shift right: [1, 1, 2, 3, 4]
shift left: [2, 3, 4, 5, 5]
```

### Những khác biệt quan sát được

`expanded` và `slice` là hai mảng mới. `expanded` dài hơn nguồn nên có hai số 0 ở cuối. `slice` bắt đầu lại từ chỉ số 0 trong kết quả.

`System.arraycopy` không thay tham chiếu `target` sang mảng khác. Nó ghi vào chính mảng mà `targetAlias` cũng đang trỏ tới, nên tham chiếu khác này nhìn thấy dữ liệu được ghi.

Các ô đích ngoài vùng chỉ số 2 và 3 vẫn mang giá trị -1. Không có quy tắc “xóa phần còn lại” sau thao tác sao chép.

Khi nguồn và đích là hai mảng nguyên thủy khác nhau, việc ghi đích không sửa nguồn. Trong hai ví dụ dịch phần tử, nguồn và đích cố ý là cùng một mảng nên chính mảng đó thay đổi.

## 5. Vùng chồng lấp: không cần tự chọn chiều lặp

Với thao tác dịch phải:

```text
trước: [1 2 3 4 5]
lấy:    └─────┘       nguồn chỉ số 0..3
ghi:      └─────┘     đích chỉ số 1..4
sau:   [1 1 2 3 4]
```

Nếu tự viết vòng lặp từ trái sang phải và ghi đè ngay trong cùng mảng, giá trị vừa ghi có thể trở thành nguồn cho lần lặp sau, làm sai dữ liệu.

`System.arraycopy` hỗ trợ vùng chồng lấp trên cùng mảng. Có thể suy luận như thể đoạn nguồn được giữ riêng trước khi ghi đích. Đây là quy tắc về kết quả, không phải cam kết rằng mỗi lần gọi đều cấp phát một mảng tạm thực tế.

Khi dịch trái, ô cuối cùng vẫn giữ giá trị cũ vì nó nằm ngoài vùng ghi. Ứng dụng quản lý một bộ đệm còn phải cập nhật số phần tử đang dùng. Với mảng tham chiếu, sau khi xóa một phần tử bằng dịch trái, thường còn cần gán `null` vào ô dư để tránh giữ tham chiếu không còn cần thiết.

Không dùng `Arrays.copyOfRange` để mong dịch tại chỗ: nó trả về một mảng mới. Nếu muốn dùng kết quả mới, bên gọi phải lưu hoặc trả kết quả đó.

## 6. Khác biệt về giới hạn: arraycopy không bù dữ liệu

Với `System.arraycopy`, đoạn nguồn cần có đủ dữ liệu và đoạn đích cần đủ chỗ. Ta phải bảo đảm các vị trí không âm, `length >= 0`, và cả hai đoạn đều nằm trong mảng tương ứng.

Để kiểm tra mà tránh cộng tràn số, có thể diễn đạt sau khi xác nhận vị trí hợp lệ:

```text
length <= source.length - srcPos
length <= target.length - destPos
```

Nếu thiếu dữ liệu nguồn hoặc thiếu chỗ đích, phương thức báo lỗi giới hạn. Nó không tự:

- Kéo dài mảng đích.
- Chuyển ít phần tử hơn theo dung lượng còn lại.
- Bù 0 hoặc null cho phần nguồn không có.
- Bỏ qua phần nằm ngoài giới hạn.

Trong khi đó:

- `Arrays.copyOf(source, newLength)` tạo kết quả theo độ dài yêu cầu; nếu dài hơn nguồn thì có phần bù mặc định.
- `Arrays.copyOfRange(source, from, to)` cũng có thể bù khi `to` vượt cuối nguồn và `from` vẫn hợp lệ.
- Các phần bù là 0 theo kiểu số, `false` với boolean, ký tự mã 0 với char hoặc `null` với tham chiếu.

Chọn tạo mảng mới để mở rộng khác với mong đợi mảng cũ tự thay đổi kích thước. Mảng Java có độ dài cố định; gán kết quả `copyOf` cho một biến chỉ làm biến đó trỏ tới mảng khác. Những tham chiếu còn giữ mảng cũ vẫn thấy độ dài cũ.

## 7. Kiểu phần tử và khả năng ghi đích một phần

`System.arraycopy` không phải công cụ chuyển đổi mọi kiểu phần tử:

- Không tự chuyển `int[]` thành `long[]`, dù phép gán một giá trị `int` riêng lẻ sang `long` là hợp lệ.
- Không tự đóng gói `int[]` thành `Integer[]`.
- Với mảng tham chiếu, từng phần tử được chuyển phải chứa được trong kiểu thực tế của mảng đích.

Một điểm quan trọng khi đích đã có dữ liệu: nếu một phần tử tham chiếu không tương thích, các phần tử đứng trước nó trong đoạn yêu cầu có thể đã được ghi. Do đó không được coi mọi lỗi sao chép đều để đích nguyên vẹn.

Ngược lại, lỗi giới hạn hoặc kiểu mảng nguyên thủy không tương thích được phát hiện theo hợp đồng trước khi sửa đích. Không gộp hai tình huống này thành một kết luận chung “có lỗi thì không đổi gì”.

## 8. Chương trình đầy đủ: giới hạn, kiểu và phần đã ghi

Lưu tệp **ArrayCopyFailureDemo.java**:

```java
import java.util.Arrays;

public class ArrayCopyFailureDemo {
    public static void main(String[] args) {
        int[] source = {1, 2, 3};
        int[] smallTarget = {9, 9};

        try {
            System.arraycopy(source, 0, smallTarget, 0, 3);
        } catch (IndexOutOfBoundsException e) {
            System.out.println("bounds error");
        }
        System.out.println("after bounds error: "
                + Arrays.toString(smallTarget));

        long[] longTarget = {-1L, -1L, -1L};
        try {
            System.arraycopy(source, 0, longTarget, 0, 3);
        } catch (ArrayStoreException e) {
            System.out.println("primitive type mismatch");
        }
        System.out.println("after primitive mismatch: "
                + Arrays.toString(longTarget));

        Object[] mixed = {"ok", 42, "later"};
        String[] strings = {"old0", "old1", "old2"};
        try {
            System.arraycopy(mixed, 0, strings, 0, 3);
        } catch (ArrayStoreException e) {
            System.out.println("reference element mismatch");
        }
        System.out.println("after reference mismatch: "
                + Arrays.toString(strings));
    }
}
```

Chạy:

```shell
javac ArrayCopyFailureDemo.java
java ArrayCopyFailureDemo
```

Stdout:

```text
bounds error
after bounds error: [9, 9]
primitive type mismatch
after primitive mismatch: [-1, -1, -1]
reference element mismatch
after reference mismatch: [ok, old1, old2]
```

Trong trường hợp cuối, `"ok"` được ghi vào ô 0 thành công. Phần tử số 42 không thể được gán vào `String[]`, nên thao tác dừng tại đó và ô 1, ô 2 vẫn giữ dữ liệu cũ.

Khi tính toàn vẹn của đích quan trọng, có thể kiểm tra tính tương thích hoặc chuẩn bị đầy đủ kết quả trong một vùng chứa riêng trước khi công bố kết quả. Chỉ “bắt ngoại lệ rồi tiếp tục dùng đích như bản cũ” có thể làm ứng dụng sử dụng dữ liệu pha trộn.

Vùng chứa riêng cũng không tự tạo một giao dịch giữa nhiều luồng. Nếu có chia sẻ dữ liệu đồng thời, việc công bố kết quả và quyền sửa còn cần cơ chế phối hợp phù hợp.

## 9. Dùng hai nhóm API cùng nhau khi ghép mảng

Không nhất thiết phải chọn một API duy nhất cho cả thuật toán. Ví dụ ghép hai mảng có thể dùng `copyOf` để tạo vùng chứa kết quả, rồi `arraycopy` để ghi đoạn thứ hai:

```java
import java.util.Arrays;

// Phương thức thành viên, không phải chương trình độc lập.
static int[] concatenate(int[] first, int[] second) {
    int totalLength = Math.addExact(first.length, second.length);
    int[] result = Arrays.copyOf(first, totalLength);
    System.arraycopy(second, 0, result, first.length, second.length);
    return result;
}
```

Với `first = [3, 5]` và `second = [7, 9, 11]`, kết quả là `[3, 5, 7, 9, 11]`.

Từng API có vai trò rõ ràng:

1. `Math.addExact` kiểm tra phép cộng độ dài không tràn `int`.
2. `copyOf` cấp phát kết quả và đưa mảng thứ nhất vào đầu.
3. `arraycopy` đặt mảng thứ hai tại đúng vị trí sau mảng thứ nhất.

Phương thức giả định hai mảng nguồn khác `null`. Dù phép cộng không tràn, việc cấp phát vẫn có thể thất bại nếu kích thước vượt giới hạn bộ nhớ của môi trường.

Một lựa chọn tương đương là tự `new int[totalLength]` rồi gọi `arraycopy` hai lần. Lựa chọn nào rõ hơn phụ thuộc thuật toán; không nên biến khác biệt biểu đạt thành khẳng định tốc độ khi chưa đo.

## 10. Độ sâu bản sao và hiệu năng là hai câu hỏi riêng

Cả hai nhóm API đều sao chép **giá trị phần tử**. Với mảng đối tượng, giá trị phần tử là tham chiếu, nên chúng không tự tạo bản sao của từng đối tượng.

Tạo mảng đích mới giúp tách các ô của vùng chứa. Nó chưa bảo đảm hai bên độc lập khi sửa trạng thái của đối tượng phần tử đang dùng chung.

Về hiệu năng, cân nhắc công việc thực tế:

- Nếu luôn cần mảng kết quả mới, việc `new` đích trước `arraycopy` vẫn có chi phí cấp phát.
- Nếu đã có bộ đệm phù hợp, `arraycopy` cho phép ghi trực tiếp vào đó.
- Tái sử dụng đích có thể giảm cấp phát nhưng cần quản lý phần dữ liệu cũ, quyền sở hữu và việc có luồng khác đang dùng đích hay không.
- Không gọi `arraycopy` là “luôn nhanh hơn” chỉ vì đây là phương thức của lớp `System`; cần đo với JDK, kích thước dữ liệu và cách dùng tương ứng.

Ưu tiên diễn tả đúng ý định và đúng hợp đồng trước. Việc tối ưu không nên thay đổi cách xử lý lỗi hoặc vô tình làm lộ vùng chứa dùng chung.

## 11. Các lỗi thường gặp khi đổi API

| Lỗi | Hệ quả |
| --- | --- |
| Dùng `to` của `copyOfRange` làm `length` của `arraycopy` | Sao chép sai số lượng; đúng số lượng là `to - from` |
| Quên cấp phát đích | Đích có thể là null và gây `NullPointerException` |
| Mong arraycopy tự mở rộng đích | Lỗi giới hạn |
| Ghi vào đích đang được nơi khác sử dụng | Nơi đó nhìn thấy dữ liệu bị ghi đè |
| Bỏ qua lỗi không tương thích phần tử tham chiếu | Đích có thể đã đổi một phần |
| Dùng tạo mảng mới để thay cho dịch tại chỗ nhưng bỏ kết quả | Mảng đang dùng không thay đổi |
| Cho rằng đổi API tạo sao chép sâu | Các đối tượng phần tử vẫn được chia sẻ |

Ví dụ đổi đúng một đoạn hoàn toàn nằm trong nguồn:

```java
import java.util.Arrays;

// Đoạn minh họa; 0 <= from <= to <= source.length.
int[] slice1 = Arrays.copyOfRange(source, from, to);

int[] slice2 = new int[to - from];
System.arraycopy(source, from, slice2, 0, to - from);
```

Điều kiện `to <= source.length` ở đây rất quan trọng. Nếu bản ban đầu chủ ý cho phép `copyOfRange` bù phần vượt nguồn, thay bằng một lời gọi `arraycopy` có cùng số lượng sẽ không còn hành vi tương đương.

## 12. Thực hành chọn API

1. Bạn cần trả về mảng gồm bốn phần tử đầu của nguồn. Chọn API diễn tả trực tiếp nhu cầu và nêu điều gì xảy ra nếu nguồn ngắn hơn bốn.
2. Bạn có bộ đệm dài 20, cần ghi ba phần tử vào vị trí 10 và giữ nguyên mọi ô khác. Xác định năm tham số của `arraycopy`.
3. Bạn cần chèn một phần tử vào vị trí giữa của vùng dữ liệu đang dùng trong mảng còn chỗ trống. Vẽ đoạn cần dịch phải, rồi xác định vị trí ghi phần tử mới.
4. Với nguồn `Object[]` chứa chuỗi rồi số nguyên, dự đoán mảng `String[]` đích sau khi sao chép thất bại.
5. Viết lại hàm ghép mảng bằng một lần cấp phát và hai lần `arraycopy`; kiểm tra trường hợp một hoặc cả hai nguồn rỗng.

Câu hỏi quyết định khi chọn API là: cần **mảng kết quả mới**, **đoạn con mới**, hay **ghi vào một vùng cụ thể của mảng hiện có**? Sau đó mới xét giới hạn, kiểu phần tử, quyền sở hữu và đường xử lý lỗi.
