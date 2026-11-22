# swap, rotate và replaceAll

## 1. Ba cách thay đổi một List đang có

Một danh sách tác vụ có thể cần đổi chỗ hai mục, đưa nhóm cuối lên đầu hoặc thay tất cả nhãn cũ bằng nhãn mới. Cả ba nhu cầu đều giữ nguyên số vị trí trong danh sách, nhưng tác động lên dữ liệu theo những quy tắc khác nhau.

Lớp tiện ích `java.util.Collections` có các phương thức tĩnh phục vụ những thao tác này:

| Phương thức | Câu hỏi nó giải quyết | Đối tượng được thay đổi | Giá trị trả về |
| --- | --- | --- | --- |
| `swap(list, i, j)` | Hai vị trí nào cần đổi phần tử cho nhau? | Chính List truyền vào | `void` |
| `rotate(list, distance)` | Cả dãy cần dịch vòng bao nhiêu vị trí? | Chính List truyền vào | `void` |
| `replaceAll(list, oldVal, newVal)` | Mọi lần xuất hiện của giá trị nào cần được thay? | Chính List truyền vào | `boolean` cho biết có phần tử khớp |

Đây là các thao tác **tại chỗ**: gọi phương thức rồi đọc lại List ấy để xem kết quả. Chúng không trả một List mới đã được biến đổi. Nếu hai biến đang giữ cùng một List, việc sửa qua một biến cũng được quan sát qua biến còn lại.

Có thể hình dung List như dãy ô đánh số từ 0. `swap` đổi những gì hai ô đang giữ; `rotate` sắp lại các tham chiếu theo vòng; `replaceAll` tìm các ô có phần tử khớp rồi gán giá trị thay thế. Các thao tác này không tự sao chép sâu đối tượng phần tử.

Khác biệt quan trọng là cách xác định mục tiêu: `swap` dùng chỉ số, `rotate` dùng khoảng dịch, còn `replaceAll` dùng điều kiện bằng nhau của giá trị. Vì vậy, đầu vào đúng cho thao tác này chưa chắc đúng hoặc có ý nghĩa với thao tác kia.

Người học cần biết List có thứ tự, chỉ số bắt đầu từ 0, `get` đọc phần tử và `set` thay phần tử tại một vị trí. Tất cả chương trình dưới đây độc lập, dùng Java 17. Lưu mỗi chương trình đúng tên tệp; các lệnh biên dịch và stdout được ghi ngay sau mã.

## 2. Không đổi kích thước vẫn cần quyền sửa

Một List có thể cho thay phần tử nhưng không cho tăng hoặc giảm số phần tử. Đây là điều kiện đủ cho nhiều thao tác trong bài, vì chúng chủ yếu cần khả năng thay phần tử qua `set` hoặc cơ chế tương ứng của bộ duyệt List.

Ví dụ, `Arrays.asList(array)` tạo một List cố định kích thước, liên hệ trực tiếp với mảng. Không thể dùng nó để thêm một vị trí mới, nhưng có thể thay phần tử ở vị trí đã tồn tại. Các tiện ích thay tham chiếu phần tử có thể hoạt động trên List đó và thay đổi được quan sát ở mảng.

Ngược lại, List từ `List.of`, `List.copyOf` hoặc một lớp bọc chỉ đọc không cho phép thay phần tử. Việc `swap` và `rotate` giữ nguyên `size()` không làm chúng trở thành thao tác chỉ đọc. Lời gọi cần sửa vẫn có thể bị từ chối bằng `UnsupportedOperationException`.

Nếu cần kết quả riêng từ nguồn chỉ đọc, chuẩn bị một List có thể sửa, chẳng hạn `new ArrayList<>(source)`, rồi áp dụng tiện ích lên bản riêng. Quyết định này còn thay đổi quan hệ với nguồn: người dùng giữ nguồn cũ không thấy các thao tác trên phần chứa của bản sao.

Không dùng kiểu `List<?>` trong chữ ký `swap` hay `rotate` để suy ra tham số chỉ đọc. Hai phương thức có thể chuyển những tham chiếu đã nằm trong chính List sang các vị trí khác mà không cần nhận một phần tử mới từ bên ngoài. Khả năng sửa thực tế phụ thuộc đối tượng List.

## 3. swap: đổi đúng hai vị trí

Với `Collections.swap(list, i, j)`, cả `i` lẫn `j` phải nằm trong khoảng từ 0 đến `list.size() - 1`. Chỉ số bằng `size()` không hợp lệ cho một vị trí phần tử hiện có.

Nếu hai chỉ số khác nhau, phần tử cũ ở `i` sang `j` và phần tử cũ ở `j` sang `i`. Những vị trí khác giữ nguyên. Nếu hai chỉ số giống nhau và lời gọi hoàn tất bình thường, nội dung không đổi. Không dùng ca không có thay đổi ấy để đoán khả năng sửa của mọi loại List.

Lưu thành `SwapPositionsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class SwapPositionsDemo {
    public static void main(String[] args) {
        List<String> values = new ArrayList<>(List.of("A", "B", "C", "D"));
        List<String> alias = values;
        Collections.swap(values, 0, 3);
        System.out.println("afterSwap=" + values);
        System.out.println("alias=" + alias);

        Collections.swap(values, 1, 1);
        System.out.println("sameIndex=" + values);
        System.out.println("size=" + values.size());

        try {
            Collections.swap(values, 0, values.size());
        } catch (IndexOutOfBoundsException e) {
            System.out.println("badIndex=IndexOutOfBoundsException");
        }

        try {
            Collections.swap(values, -1, 0);
        } catch (IndexOutOfBoundsException e) {
            System.out.println("negativeIndex=IndexOutOfBoundsException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 SwapPositionsDemo.java
java SwapPositionsDemo
```

Stdout:

```text
afterSwap=[D, B, C, A]
alias=[D, B, C, A]
sameIndex=[D, B, C, A]
size=4
badIndex=IndexOutOfBoundsException
negativeIndex=IndexOutOfBoundsException
```

Dòng đầu cho thấy hai đầu của dãy đã đổi chỗ. Dòng `alias` có cùng nội dung vì đó là một biến khác giữ chính List đang được sửa; không có bản sao mới được tạo bởi `swap`.

Lời gọi dùng cùng chỉ số 1 không đổi dữ liệu. Hai ca lỗi sau đó kiểm tra riêng cận trên và chỉ số âm. Việc List có bốn phần tử không có nghĩa chỉ số 4 hợp lệ: các vị trí của nó là 0, 1, 2, 3.

`swap` không tìm theo giá trị. Nếu List chứa hai phần tử bằng nhau ở hai vị trí khác nhau, phương thức vẫn được chỉ định bằng chỉ số. Nó cũng không sắp xếp toàn bộ List và không cần một Comparator để xác định phần tử nào “lớn hơn”.

Một cách tự mô phỏng là giữ tạm phần tử ở vị trí đầu, gán phần tử thứ hai vào vị trí đầu rồi gán phần tử tạm vào vị trí thứ hai. Điều cần hiểu là sự bảo toàn hai phần tử, không phải một chuỗi gán cụ thể mà mọi bản triển khai phải dùng.

Hợp đồng chỉ số và kết quả được mô tả tại [Collections.swap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#swap(java.util.List,int,int)).

## 4. rotate: dịch vòng và chiều của khoảng dịch

Xét dãy `[A, B, C, D, E]`. Dịch vòng nghĩa là phần tử vượt qua một đầu sẽ quay lại đầu còn lại. Không có vị trí mới được thêm và không có phần tử nào bị loại bỏ.

- Khoảng dịch dương đưa các phần tử sang phải.
- Khoảng dịch âm đưa các phần tử sang trái.
- Khoảng dịch bằng 0 giữ nguyên dãy khi thao tác hoàn tất.
- Khoảng dịch có thể lớn hơn kích thước; các vòng đầy đủ không làm thay đổi kết quả cuối.

Ví dụ, dịch phải một vị trí đưa E lên đầu, tạo `[E, A, B, C, D]`. Dịch trái hai vị trí đưa A và B xuống cuối theo đúng thứ tự của chúng, tạo `[C, D, E, A, B]`.

Với List không rỗng có n phần tử, có thể dùng số học modulo để dự đoán. Chuẩn hóa khoảng dịch thành r trong đoạn từ 0 đến n - 1 bằng `Math.floorMod(distance, n)`. Sau đó, theo nghĩa toán học:

`vị trí mới của phần tử cũ ở i = (i + r) mod n`

Đây là công thức vị trí, không phải yêu cầu tự viết lại thuật toán thư viện. Nếu triển khai phép cộng trong Java với chỉ số rất lớn, phải tính đến tràn số int; không xem biểu thức toán học là luôn an toàn để chép nguyên xi vào mọi phép tính int.

Với n bằng 5 và r bằng 2:

| Phần tử ban đầu | Chỉ số cũ | Chỉ số mới |
| --- | --- | --- |
| A | 0 | 2 |
| B | 1 | 3 |
| C | 2 | 4 |
| D | 3 | 0 |
| E | 4 | 1 |

Đọc theo chỉ số mới cho kết quả `[D, E, A, B, C]`. Cũng có thể tách dãy thành hai khối: ba phần tử đầu và hai phần tử cuối; đưa khối cuối lên đầu, giữ thứ tự bên trong từng khối.

Với khoảng dịch âm, không dùng trị tuyệt đối để quyết định kết quả. `floorMod` đưa số âm về phần dư không âm phù hợp với vòng. Trường hợp List rỗng phải được xét riêng khi tự tính modulo, vì không được chia lấy dư cho 0.

## 5. Thí nghiệm rotate với số âm, số lớn và List rỗng

Lưu thành `RotateDistanceDemo.java`. Mỗi khoảng dịch được áp dụng lên một ArrayList mới từ cùng dữ liệu gốc, nên các dòng không phải các lần dịch cộng dồn.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class RotateDistanceDemo {
    public static void main(String[] args) {
        List<String> base = List.of("A", "B", "C", "D", "E");
        int[] distances = {1, -2, 7, Integer.MIN_VALUE, 0};
        for (int distance : distances) {
            List<String> values = new ArrayList<>(base);
            Collections.rotate(values, distance);
            System.out.println("distance=" + distance + " -> " + values);
        }

        int normalized = Math.floorMod(Integer.MIN_VALUE, base.size());
        System.out.println("minValueNormalized=" + normalized);

        List<String> roundTrip = new ArrayList<>(base);
        Collections.rotate(roundTrip, 2);
        Collections.rotate(roundTrip, -2);
        System.out.println("roundTrip=" + roundTrip);

        List<String> empty = new ArrayList<>();
        Collections.rotate(empty, 8);
        System.out.println("empty=" + empty);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 RotateDistanceDemo.java
java RotateDistanceDemo
```

Stdout:

```text
distance=1 -> [E, A, B, C, D]
distance=-2 -> [C, D, E, A, B]
distance=7 -> [D, E, A, B, C]
distance=-2147483648 -> [D, E, A, B, C]
distance=0 -> [A, B, C, D, E]
minValueNormalized=2
roundTrip=[A, B, C, D, E]
empty=[]
```

Khoảng dịch 7 tương đương dịch phải 2 đối với năm phần tử. Khoảng dịch `Integer.MIN_VALUE` cũng chuẩn hóa thành 2 trong trường hợp này; chương trình cho cùng kết quả tương ứng. Không cần giới hạn khoảng dịch vào một đoạn nhỏ trước khi truyền cho `Collections.rotate`.

Ca `roundTrip` dịch phải hai rồi dịch trái hai trên cùng List, nên quay lại dãy ban đầu. Dịch vòng không đảo thứ tự toàn bộ như thao tác reverse; những phần tử đi qua biên tiếp tục nối vòng theo thứ tự của dãy.

Ca List rỗng được gọi trực tiếp với `Collections.rotate` và vẫn rỗng. Trong mã tự dự đoán, không gọi `Math.floorMod(distance, empty.size())`; đây là phép tính riêng không hợp lệ do mẫu số bằng 0, không phải điều mà chương trình trên đã làm.

Nếu tự tính khoảng dịch ngược bằng `-distance`, cần chú ý `Integer.MIN_VALUE`: đổi dấu giá trị ấy trong kiểu int không tạo ra số dương đối xứng biểu diễn được. Khi cần thao tác nghịch đảo cho List không rỗng, có thể dựa trên khoảng dịch đã chuẩn hóa phù hợp thay vì phủ định tùy ý một int đầu vào. Ví dụ đang kiểm chứng cặp 2 và -2, không khẳng định mọi phép đổi dấu int đều an toàn.

Xem quy tắc vị trí và miền khoảng dịch trong [Collections.rotate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#rotate(java.util.List,int)).

## 6. Collections.replaceAll: thay mọi lần xuất hiện khớp giá trị

Chữ ký của tiện ích là `Collections.replaceAll(List<T> list, T oldVal, T newVal)`. Phương thức xét các phần tử trong List và thay những phần tử khớp `oldVal` bằng `newVal`.

Điều kiện khớp được hiểu như sau:

- Nếu `oldVal` là null, phần tử null là phần tử khớp.
- Nếu `oldVal` khác null, dùng `oldVal.equals(element)`.

Do đó, hai đối tượng khác tham chiếu nhưng bằng nhau theo `equals` vẫn có thể khớp. Không dùng `==` để dự đoán việc thay giá trị thông thường. So sánh ở đây cũng không dựa trên Comparator hay thứ tự sắp xếp.

Phương thức thay **tất cả** vị trí khớp, không dừng ở vị trí đầu tiên. Thứ tự các vị trí được giữ, kích thước được giữ, nhưng số lần xuất hiện của các giá trị có thể thay đổi vì giá trị cũ được thay bằng giá trị mới.

Giá trị boolean nói rằng List có ít nhất một phần tử khớp điều kiện hay không. Nó không là số phần tử đã thay, cũng không là bằng chứng rằng nội dung quan sát theo `equals` đã khác trước. Nếu thay `"green"` bằng `"green"` trong List có green, kết quả boolean vẫn là true.

`newVal` phải phù hợp với kiểu và các ràng buộc phần tử của List. Với một List cho phép null, có thể dùng null làm giá trị cần tìm hoặc giá trị thay thế. Không suy từ khả năng đó rằng mọi List đều nhận null hoặc đều cho phép `set`.

Việc thay được thực hiện ở tham chiếu phần tử của List. Nó không gọi một setter nghiệp vụ trên đối tượng cũ và không tự tạo một bản sao mới của `newVal` cho từng vị trí. Nếu `newVal` là một đối tượng có thể sửa, những vị trí được thay có thể cùng giữ đối tượng đó; cần hiểu mức chia sẻ khi dùng kiểu phần tử như vậy.

## 7. Thí nghiệm replaceAll và phân biệt phương thức cùng tên trên List

Lưu thành `ReplaceMatchingValuesDemo.java`. Một chuỗi red được tạo bằng `new String` để nhấn mạnh rằng khớp dựa trên nội dung bằng nhau, không yêu cầu cùng một tham chiếu String. Null được chuẩn bị bằng một List cho phép null.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Locale;

public class ReplaceMatchingValuesDemo {
    public static void main(String[] args) {
        List<String> values = new ArrayList<>(
                Arrays.asList("red", null, new String("red"), "blue"));

        boolean found = Collections.replaceAll(values, "red", "green");
        System.out.println("foundRed=" + found);
        System.out.println("afterRed=" + values);

        boolean foundNull = Collections.replaceAll(values, null, "unknown");
        System.out.println("foundNull=" + foundNull);
        System.out.println("afterNull=" + values);

        boolean absent = Collections.replaceAll(values, "black", "white");
        System.out.println("absent=" + absent);

        boolean sameValue = Collections.replaceAll(values, "green", "green");
        System.out.println("sameValue=" + sameValue);
        System.out.println("afterSameValue=" + values);

        values.replaceAll(value -> value.toUpperCase(Locale.ROOT));
        System.out.println("afterOperator=" + values);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ReplaceMatchingValuesDemo.java
java ReplaceMatchingValuesDemo
```

Stdout:

```text
foundRed=true
afterRed=[green, null, green, blue]
foundNull=true
afterNull=[green, unknown, green, blue]
absent=false
sameValue=true
afterSameValue=[green, unknown, green, blue]
afterOperator=[GREEN, UNKNOWN, GREEN, BLUE]
```

Sau lần thay đầu tiên, cả hai vị trí red đều thành green, còn null và blue được giữ. Lần thay thứ hai chỉ nhắm các phần tử null nên tạo nhãn unknown tại đúng vị trí đó.

Không có black trong List, vì vậy biến `absent` là false. Khi thay green bằng green, biến `sameValue` là true, trong khi nội dung hiển thị vẫn như trước lần gọi. Hai dòng này giúp đọc đúng ý nghĩa của kết quả boolean.

Dòng cuối gọi `values.replaceAll(...)`, tức phương thức của chính List. Nó nhận một hàm một đối số rồi dùng kết quả hàm để thay từng phần tử. Ở thời điểm này null đã được thay thành unknown, nên phép chuyển thành chữ hoa áp dụng được cho mọi phần tử String.

| Tiêu chí | `Collections.replaceAll(list, oldVal, newVal)` | `list.replaceAll(operator)` |
| --- | --- | --- |
| Nơi khai báo | Lớp tiện ích Collections | Giao diện List |
| Đầu vào chính | Một giá trị cần tìm và một giá trị thay | Hàm biến đổi từng phần tử |
| Phần tử được xử lý | Các phần tử khớp giá trị cũ | Từng phần tử theo kết quả hàm |
| Giá trị trả về | `boolean` cho biết có khớp | `void` |
| Ví dụ nhu cầu | Đổi mọi nhãn cũ sang một nhãn mới | Chuẩn hóa hoặc tính giá trị mới theo từng phần tử |

`Locale.ROOT` trong chương trình làm phép đổi chữ hoa không phụ thuộc ngôn ngữ mặc định của máy. Phần này minh họa cách phân biệt hai API cùng tên; mục tiêu chính của bài vẫn là tiện ích Collections thay theo giá trị.

Nếu chỉ cần thay đúng một vị trí đã biết, `list.set(index, value)` diễn đạt mục tiêu khác với việc thay tất cả giá trị bằng nhau. Nếu cần một điều kiện tùy ý và mỗi phần tử tạo kết quả riêng, phương thức nhận hàm của List có thể phù hợp hơn. Chọn theo quy tắc biến đổi cần thực hiện.

Hợp đồng tương ứng: [Collections.replaceAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#replaceAll(java.util.List,T,T)) và [List.replaceAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#replaceAll(java.util.function.UnaryOperator)).

## 8. Thí nghiệm khả năng sửa: cố định kích thước và chỉ đọc

Lưu thành `ListMutationSupportDemo.java`. Chương trình thử ba tiện ích trên List từ mảng, rồi trên một lớp bọc chỉ đọc. Các ca bị chặn đều thực sự yêu cầu thay đổi dữ liệu, không dựa vào tình huống không có tác dụng.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class ListMutationSupportDemo {
    public static void main(String[] args) {
        String[] array = {"A", "B", "C", "A"};
        List<String> fixed = Arrays.asList(array);
        Collections.swap(fixed, 0, 1);
        Collections.rotate(fixed, 1);
        boolean found = Collections.replaceAll(fixed, "A", "X");
        System.out.println("fixed=" + fixed);
        System.out.println("array=" + Arrays.toString(array));
        System.out.println("found=" + found);
        try {
            fixed.add("new");
        } catch (UnsupportedOperationException e) {
            System.out.println("fixedAdd=UnsupportedOperationException");
        }

        List<String> readOnly = Collections.unmodifiableList(
                new ArrayList<>(List.of("A", "B", "C")));
        try {
            Collections.swap(readOnly, 0, 1);
        } catch (UnsupportedOperationException e) {
            System.out.println("readOnlySwap=UnsupportedOperationException");
        }
        try {
            Collections.rotate(readOnly, 1);
        } catch (UnsupportedOperationException e) {
            System.out.println("readOnlyRotate=UnsupportedOperationException");
        }
        try {
            Collections.replaceAll(readOnly, "A", "Z");
        } catch (UnsupportedOperationException e) {
            System.out.println("readOnlyReplace=UnsupportedOperationException");
        }
        System.out.println("readOnly=" + readOnly);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ListMutationSupportDemo.java
java ListMutationSupportDemo
```

Stdout:

```text
fixed=[X, B, X, C]
array=[X, B, X, C]
found=true
fixedAdd=UnsupportedOperationException
readOnlySwap=UnsupportedOperationException
readOnlyRotate=UnsupportedOperationException
readOnlyReplace=UnsupportedOperationException
readOnly=[A, B, C]
```

Theo dõi List từ mảng qua từng bước:

| Bước | Nội dung |
| --- | --- |
| Ban đầu | `[A, B, C, A]` |
| Đổi vị trí 0 và 1 | `[B, A, C, A]` |
| Dịch phải một vị trí | `[A, B, A, C]` |
| Thay mọi A bằng X | `[X, B, X, C]` |

Dòng in mảng có cùng nội dung cuối vì List cố định kích thước đang dựa trên mảng đó. Các thao tác `set` được phép, còn `add` cần tăng kích thước nên bị từ chối.

Đối với `readOnly`, cả ba yêu cầu sửa đều bị chặn. Giữ nguyên số phần tử không đủ để được phép thao tác: quyền thay tham chiếu ở một vị trí cũng là quyền sửa dữ liệu.

Bảng so sánh đúng cần tách hai khả năng:

| Loại List trong ví dụ | Thay phần tử ở vị trí có sẵn | Tăng/giảm số phần tử |
| --- | --- | --- |
| ArrayList thông thường | Có | Có |
| List từ Arrays.asList | Có | Không |
| Lớp bọc Collections.unmodifiableList | Không qua lớp bọc | Không qua lớp bọc |

Không lập trình bằng cách gọi thử một tiện ích rồi bắt ngoại lệ để đoán loại List. Nếu phương thức của mình có trách nhiệm tạo kết quả đã biến đổi, chuẩn bị List phù hợp ngay từ đầu. Nếu phương thức yêu cầu sửa chính List của bên gọi, nêu rõ điều kiện hỗ trợ thay phần tử.

Các thuật toán sửa dữ liệu của Collections có quy tắc cho phép khác biệt về việc ném ngoại lệ trong một số lời gọi không có tác dụng. Vì vậy, những ca như không tìm thấy giá trị, khoảng dịch không đổi dãy hoặc hai chỉ số trùng nhau không nên được dùng làm phép thử phổ quát về khả năng sửa.

Quan hệ giữa mảng và List cùng khả năng giữ cố định kích thước được mô tả ở [Arrays.asList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)).

## 9. Áp dụng lên subList: phạm vi nhỏ, tác động lên List cha

Nếu chỉ muốn biến đổi một đoạn, có thể lấy một khung nhìn (view) bằng `subList(fromIndex, toIndex)` rồi truyền view đó cho tiện ích. Cận đầu được tính vào, cận cuối không được tính vào. Chỉ số khi gọi `swap` trên view là chỉ số cục bộ của đoạn, không phải chỉ số trực tiếp của List cha.

Giả sử List cha là `[head, A, B, C, D, tail]`. View `subList(1, 5)` gồm bốn phần tử `[A, B, C, D]`. Vị trí 0 của view tương ứng với vị trí 1 của cha; vị trí 3 tương ứng với vị trí 4.

View không tự tạo bản sao. Khi sửa phần tử qua view, List cha nhận thay đổi ở đoạn tương ứng. Những phần tử ngoài đoạn không là mục tiêu của tiện ích.

Lưu thành `SubListUtilitiesDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class SubListUtilitiesDemo {
    public static void main(String[] args) {
        List<String> parent = new ArrayList<>(
                List.of("head", "A", "B", "C", "D", "tail"));
        List<String> window = parent.subList(1, 5);

        Collections.swap(window, 0, 3);
        System.out.println("parentAfterSwap=" + parent);

        Collections.rotate(window, -1);
        System.out.println("parentAfterRotate=" + parent);

        boolean found = Collections.replaceAll(window, "A", "X");
        System.out.println("found=" + found);
        System.out.println("window=" + window);
        System.out.println("parentAfterReplace=" + parent);

        List<String> move = new ArrayList<>(List.of("P", "Q", "R", "S", "T"));
        Collections.rotate(move.subList(1, 4), -1);
        System.out.println("moveOne=" + move);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 SubListUtilitiesDemo.java
java SubListUtilitiesDemo
```

Stdout:

```text
parentAfterSwap=[head, D, B, C, A, tail]
parentAfterRotate=[head, B, C, A, D, tail]
found=true
window=[B, C, X, D]
parentAfterReplace=[head, B, C, X, D, tail]
moveOne=[P, R, S, Q, T]
```

Hai phần tử head và tail không đổi qua cả ba thao tác trên window. Các dòng in List cha cho thấy đoạn giữa đã đổi chỗ, dịch vòng rồi thay giá trị. Dòng `window` cho thấy kết quả cục bộ của chính đoạn đó.

Ca `moveOne` dùng dịch vòng để di chuyển một phần tử mà giữ thứ tự các phần tử còn lại trong đoạn. Đoạn từ chỉ số 1 đến trước 4 là `[Q, R, S]`. Dịch trái một vị trí tạo `[R, S, Q]`; khi đặt trong List cha, Q được chuyển từ chỉ số 1 đến chỉ số 3.

Tổng quát, khi cần chuyển phần tử ở j sang k với j nhỏ hơn hoặc bằng k, có thể dịch trái một vị trí trên đoạn từ j đến trước k + 1. Đó là cách xử lý vị trí trong một đoạn, không yêu cầu xóa phần tử rồi thêm một vị trí mới.

Điều này đặc biệt hữu ích khi List hỗ trợ thay phần tử nhưng không hỗ trợ đổi kích thước. Tuy nhiên, phải tính đúng cận cuối: dùng k thay cho k + 1 sẽ bỏ chính vị trí đích ra khỏi đoạn.

Trong khi đang sử dụng view, không tùy ý thêm/xóa cấu trúc ở List cha qua một đường khác rồi tiếp tục coi view là hợp lệ. Hợp đồng của `subList` có điều kiện về thay đổi cấu trúc bên ngoài view. Ví dụ chỉ thay phần tử, không xen thêm các thao tác làm thay kích thước nguồn.

Nếu muốn biến đổi một đoạn độc lập mà không sửa cha, tạo một List riêng từ đoạn trước khi gọi tiện ích. Quyền sửa, phạm vi và quan hệ với nguồn là ba quyết định cần xem cùng nhau.

## 10. Cơ chế và chi phí phụ thuộc kiểu List

Hiểu cách List truy cập phần tử giúp chọn thao tác đúng. Một phương thức nhận giao diện List không có nghĩa mọi List có cùng chi phí cho `get(index)` và `set(index, value)`.

Với [ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html), các thao tác get/set có thời gian hằng số. Đổi hai vị trí chỉ cần một số ít thao tác truy cập và thay phần tử, nên swap có chi phí hằng số theo kích thước trong trường hợp thông thường này.

Với [LinkedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html), truy cập bằng chỉ số phải đi từ đầu hoặc cuối đến vị trí thích hợp. Đổi hai vị trí ở giữa một List lớn có thể tốn thời gian theo chiều dài đường duyệt. Không áp dụng kết luận về ArrayList cho mọi List chỉ vì chữ ký tiện ích giống nhau.

Đối với rotate, cần phân biệt kết quả và một cách triển khai kết quả:

- Kết quả được xác định bằng khoảng dịch vòng và vị trí phần tử.
- Bản triển khai JDK có thể chuyển phần tử theo các chu trình vị trí, hoặc xử lý các đoạn bằng những lần đảo thứ tự, tùy kích thước và khả năng truy cập của List.

Mô tả thuật toán trong Javadoc của Collections là thông tin về bản triển khai, không buộc mọi phiên bản phải giữ cùng một chuỗi lệnh nội bộ. Điều quan trọng khi sử dụng là kết quả đúng và List có quyền thay phần tử. Không tự dịch từng bước một lặp lại hàng triệu lần chỉ vì distance rất lớn; số vòng đầy đủ đã không làm thay đổi kết quả mong muốn.

ReplaceAll theo giá trị cần xét các phần tử để tìm mọi lần khớp. Với các List thông dụng và phép equals có chi phí hằng số, chi phí duyệt thường tuyến tính theo số phần tử. Nếu equals là phép so sánh nội dung lớn, phải tính thêm chi phí so sánh ấy.

Một view subList có thể giảm phạm vi cần xét xuống đoạn liên quan, nhưng chi phí vẫn phụ thuộc cách List nền thực hiện truy cập. Không cho rằng tạo view đã sao chép dữ liệu sang một cấu trúc có chi phí khác.

Các thao tác trong bài cũng không công bố một giao dịch cập nhật nguyên tử với các luồng khác. Khi List dùng chung và có truy cập đồng thời, cần cơ chế phối hợp phù hợp cho toàn bộ thao tác nghiệp vụ. Giữ nguyên size không đồng nghĩa với việc các thay đổi phần tử có thể được thực hiện tùy ý đồng thời.

## 11. Đọc ngoại lệ và giữ đúng phạm vi tác động

| Tình huống | Cách đọc và xử lý |
| --- | --- |
| swap nhận chỉ số âm hoặc bằng size | Chỉ số không nằm trong phạm vi phần tử hiện có; kiểm tra cả hai cận |
| rotate nhận số âm hoặc lớn hơn size | Khoảng dịch đó hợp lệ; kiểm tra lại chiều và phép chuẩn hóa nếu dự đoán sai |
| Tự tính modulo với size bằng 0 | Tách trường hợp rỗng trước phép tính; không gán lỗi số học ấy cho rotate |
| Tiện ích sửa một List chỉ đọc | Cần List hỗ trợ thay phần tử hoặc tạo bản riêng có thể sửa |
| List cố định kích thước vẫn cho swap/rotate | Điều này phù hợp khi List hỗ trợ set; không đồng nhất với quyền add/remove |
| replaceAll trả true nhưng nội dung in không đổi | Có phần tử khớp; boolean không là phép đo mức thay đổi nội dung |
| replaceAll không khớp đối tượng theo dự đoán | Xem lại equals của oldVal và kiểu phần tử; không dùng định danh hay Comparator để thay quy tắc khớp |
| Dùng chỉ số cha khi swap trên subList | Chuyển sang chỉ số cục bộ của view |
| Biến đổi một đoạn rồi cha cũng đổi | Đoạn là view; tạo List riêng nếu cần kết quả độc lập |

Nếu chính đối tượng List truyền vào là null, các tiện ích ném `NullPointerException` theo hợp đồng Collections. Phân biệt trường hợp này với việc một List hợp lệ có chứa phần tử null: ví dụ replaceAll đã xử lý được phần tử null vì List ấy cho phép.

Các phép sửa thư viện không tự kiểm tra mọi quy tắc nghiệp vụ của ứng dụng. Một List có thể cho thay phần tử nhưng kiểu kiểm tra dữ liệu hoặc mã equals của phần tử có thể phát sinh lỗi trong quá trình chạy. Không suy rằng luôn có cơ chế hoàn tác toàn bộ những gì đã thực hiện trước lỗi.

Nếu cần bảo toàn dữ liệu nguồn khi việc biến đổi thất bại, lựa chọn thực hiện trên dữ liệu riêng rồi kiểm tra/công bố kết quả theo quy trình phù hợp. Chỉ thêm try/catch quanh một thao tác tại chỗ không tự làm nó thành cập nhật “tất cả hoặc không có gì”.

Khi kiểm chứng, in hoặc so sánh cả nội dung và kích thước trước–sau. Với swap và rotate, kiểm tra thêm rằng các lần xuất hiện của phần tử vẫn được bảo toàn. Với replaceAll, xác định rõ các vị trí khớp; số lần xuất hiện của giá trị mới có thể tăng dù tổng số vị trí không đổi.

## 12. Thực hành từ dự đoán đến kiểm chứng

### Bài 1: Đổi chỗ hai mục được chọn

Nguồn là `[draft, review, publish, archive]`. Hãy đổi vị trí 1 và 3, dự đoán kết quả trước khi chạy, rồi kiểm tra kích thước.

Kết quả mong đợi là `[draft, archive, publish, review]`, kích thước vẫn bằng bốn. Thử thêm ca chỉ số bằng size để xác định khác biệt giữa “vị trí có thể chèn trong một số API” và “vị trí phần tử hiện có để swap”.

### Bài 2: Chọn phần tử bắt đầu của một vòng

Nguồn là `[Mon, Tue, Wed, Thu, Fri]`. Cần Wed đứng đầu và thứ tự vòng tiếp tục như ban đầu.

Hãy chọn khoảng dịch trước khi gọi rotate. Dịch trái hai vị trí, tức distance bằng -2, tạo `[Wed, Thu, Fri, Mon, Tue]`. Sau đó chọn một khoảng dịch dương tương đương và kiểm chứng hai kết quả bằng nhau. Với năm phần tử, distance bằng 3 là một lựa chọn như vậy.

### Bài 3: Thay trạng thái nhưng đọc đúng boolean

Nguồn là `[open, closed, open]`. Thay mọi open bằng pending, rồi thay pending bằng pending.

Lần đầu cần tạo `[pending, closed, pending]` và trả true. Lần sau vẫn trả true vì có phần tử khớp, dù chuỗi hiển thị không khác. Thêm ca tìm một trạng thái không có để kiểm tra nhánh false.

### Bài 4: Chỉ xoay đoạn giữa

Nguồn là `[L, A, B, C, R]`. Cần dịch phải một vị trí trong đoạn A, B, C, giữ L và R ở nguyên vị trí.

Hãy xác định view với cận đầu 1 và cận cuối 4. Kết quả cần là `[L, C, A, B, R]`. Kiểm tra rằng chỉ số cục bộ và cận cuối không tính vào được dùng đúng.

### Bài 5: Biến đổi List từ mảng

Tạo một mảng String rồi lấy List qua Arrays.asList. Áp dụng từng tiện ích, in cả List và mảng sau mỗi bước. Cuối cùng thử thêm một phần tử mới.

Tiêu chí đạt: các phép thay phần tử xuất hiện ở cả hai cách nhìn dữ liệu; thao tác tăng kích thước bị từ chối. Giải thích bằng hai quyền khác nhau: quyền set và quyền add/remove.

### Bài 6: Giữ nguồn chỉ đọc và tạo kết quả riêng

Đầu vào là List được tạo bằng List.of. Cần trả một danh sách đã rotate mà đầu vào vẫn như cũ.

Hãy tạo ArrayList riêng trước khi xoay. Tiêu chí đạt: nguồn giữ nội dung ban đầu, kết quả riêng đúng chiều xoay, và không phụ thuộc vào việc bắt ngoại lệ rồi mới sửa thiết kế.

## 13. Các câu hỏi kiểm tra mức hiểu

1. **Swap và rotate có trả một List mới không?** Không. Chúng trả void và tác động lên List được truyền vào.
2. **Vì sao List cố định kích thước vẫn có thể dùng được?** Vì các tiện ích không cần thêm/xóa vị trí, nhưng cần khả năng thay phần tử ở vị trí đã có.
3. **Distance dương trong rotate đi theo hướng nào?** Sang phải, với phần tử vượt cuối quay lên đầu.
4. **Khoảng dịch lớn hơn size có là lỗi không?** Không. Có thể dự đoán bằng khoảng dịch tương đương theo modulo khi List không rỗng.
5. **Collections.replaceAll dùng gì để khớp?** Dùng null khớp null hoặc oldVal.equals(element), không phải so sánh tham chiếu thông thường.
6. **Boolean true có chứng minh dữ liệu khác trước không?** Không. Nó cho biết đã có phần tử khớp điều kiện.
7. **List.replaceAll nhận gì khác?** Nó nhận một hàm biến đổi từng phần tử và trả void.
8. **Sửa subList có sửa List cha không?** Có thể tác động lên đoạn tương ứng vì subList là view, không phải bản sao.
9. **Giữ nguyên size có đồng nghĩa thao tác chỉ đọc không?** Không. Đổi hoặc thay tham chiếu phần tử vẫn là sửa List.
10. **Một dự đoán tốt cần xét những gì?** Phạm vi vị trí, chiều hoặc điều kiện khớp, quyền set của List và việc dữ liệu đang là nguồn thật, view hay bản riêng.

