# Bẫy Arrays.asList với mảng kiểu nguyên thủy

## 1. Khi ba số lại tạo một List có một phần tử

Một mảng `int[]` chứa ba số thường khiến người đọc dự đoán rằng `Arrays.asList(array)` sẽ tạo `List<Integer>` có ba phần tử. Thực tế, lời gọi thông thường với mảng đó tạo List chứa **một phần tử là cả mảng int**.

Điểm cần phân biệt là đơn vị dữ liệu:

- Một giá trị `int` có thể được đóng gói thành Integer trong ngữ cảnh phù hợp.
- Một `int[]` là một đối tượng mảng, không tự biến thành `Integer[]`.
- Một List có phần tử kiểu `int[]` chứa các mảng số, không chứa từng số nguyên ở tầng ngoài.

Bẫy này có thể xuất hiện dưới nhiều dấu hiệu: size bằng một, tìm một số bằng contains không được, gán kết quả sang `List<Integer>` không biên dịch, hoặc tạo ArrayList mới rồi vẫn chỉ có một mảng bên trong.

Để sửa đúng, cần xác định yêu cầu trước. Nếu muốn quản lý nhiều lô số, List chứa mảng có thể đúng mô hình. Nếu muốn một List các số để tìm kiếm, thêm/xóa từng số hoặc truyền cho API nhận Integer, phải thực hiện quá trình chuyển từng giá trị.

Bài này giải thích cơ chế varargs và đóng gói, kiểm chứng kiểu phần tử thực tế, rồi đưa ra các cách chuyển phù hợp. Các ví dụ chạy được dùng Java 17. Một ví dụ riêng được ghi rõ là ca lỗi biên dịch chủ đích để kiểm tra hiểu biết về kiểu.

## 2. Vì sao cơ chế đóng gói không tự đi vào từng ô mảng?

Chữ ký của Arrays.asList là `<T> List<T> asList(T... elements)`. Tham số cuối là varargs, được xử lý như một mảng `T[]` trong phương thức. T là kiểu tham chiếu, không thể là kiểu nguyên thủy int.

Với `Integer[]`, mảng có thể trực tiếp cung cấp các phần tử Integer cho tham số mảng. Với `int[]`, không có phép chuyển tự động cả mảng thành `Integer[]`. Bản thân `int[]` vẫn là một đối tượng có kiểu tham chiếu, nên nó có thể trở thành một phần tử varargs.

Trong ví dụ khai báo `List<int[]> result = Arrays.asList(source)`, có thể đọc hình dạng kiểu như sau:

| Tầng | Kiểu hoặc ý nghĩa |
| --- | --- |
| Một số trong nguồn | int |
| Đối tượng nguồn | `int[]` |
| Một phần tử List kết quả | `int[]` |
| T của lời gọi trong ví dụ | `int[]` |
| Mảng tham số varargs được chuẩn bị | `int[][]`, có một phần tử là source |
| Số phần tử của List | Một |

Mảng nguồn có bao nhiêu số không quyết định size của List ở tầng ngoài. Điều quyết định là số phần tử trong mảng varargs mà lời gọi này thực sự cung cấp.

Đóng gói tự động (autoboxing) xử lý một giá trị nguyên thủy trong ngữ cảnh phù hợp. Quy tắc đó không là một vòng lặp ngầm để tạo mảng kiểu bao. Có thể đối chiếu [JLS 17, Boxing Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.7) và [quy tắc chuẩn bị đối số varargs](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.4.2).

## 3. Thí nghiệm kiểu phần tử, tìm kiếm, mảng rỗng và null

Lưu thành `PrimitiveAsListTrapDemo.java`:

```java
import java.util.Arrays;
import java.util.List;

public class PrimitiveAsListTrapDemo {
    public static void main(String[] args) {
        int[] source = {4, 8, 15};
        List<int[]> result = Arrays.asList(source);
        System.out.println("sourceLength=" + source.length);
        System.out.println("listSize=" + result.size());
        System.out.println("elementType=" + result.get(0).getClass().getTypeName());
        System.out.println("sameArray=" + (result.get(0) == source));
        System.out.println("elementValues=" + Arrays.toString(result.get(0)));
        System.out.println("containsEight=" + result.contains(8));
        System.out.println("containsSource=" + result.contains(source));
        System.out.println("containsEqualNumbers="
                + result.contains(new int[]{4, 8, 15}));
        System.out.println("nestedDisplay=" + Arrays.deepToString(result.toArray()));

        System.out.println("emptyPrimitiveListSize="
                + Arrays.asList(new int[0]).size());
        System.out.println("emptyWrapperListSize="
                + Arrays.asList(new Integer[0]).size());
        int[] missing = null;
        List<int[]> withMissing = Arrays.asList(missing);
        System.out.println("missingListSize=" + withMissing.size());
        System.out.println("missingElementIsNull=" + (withMissing.get(0) == null));
        try {
            Arrays.asList((Integer[]) null);
        } catch (NullPointerException e) {
            System.out.println("nullWrapperArray=NullPointerException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 PrimitiveAsListTrapDemo.java
java PrimitiveAsListTrapDemo
```

Stdout:

```text
sourceLength=3
listSize=1
elementType=int[]
sameArray=true
elementValues=[4, 8, 15]
containsEight=false
containsSource=true
containsEqualNumbers=false
nestedDisplay=[[4, 8, 15]]
emptyPrimitiveListSize=1
emptyWrapperListSize=0
missingListSize=1
missingElementIsNull=true
nullWrapperArray=NullPointerException
```

`sourceLength=3` đếm số ô int trong nguồn. `listSize=1` đếm phần tử của List bên ngoài. Hai con số khác nhau vì đang đếm ở hai tầng dữ liệu.

Dòng `elementType=int[]` và phép so sánh tham chiếu cho thấy phần tử List là chính mảng nguồn. Dùng Arrays.toString trên phần tử ấy mới đọc được các số bên trong.

### 3.1. Vì sao contains(8) trả false?

Contains tìm một phần tử bằng đối số theo hợp đồng List. Ở tầng List này, phần tử là một `int[]`, không phải Integer có giá trị 8. Vì thế việc tìm số 8 không tìm sâu vào mảng.

Tìm chính source thì được vì List đang giữ tham chiếu đó. Tạo một `int[]` khác có cùng ba số không làm nó bằng source theo equals mặc định của mảng; do đó ca chứa cùng các số nhưng là một mảng khác vẫn trả false.

Nếu yêu cầu là so sánh nội dung hai mảng nguyên thủy, cần dùng phép so sánh mảng phù hợp như Arrays.equals, thay vì suy từ việc các số bên trong giống nhau rằng các đối tượng mảng bằng nhau theo equals.

Dòng nestedDisplay dùng Arrays.deepToString để nhìn rõ một tầng List ngoài và một mảng số bên trong. Không dùng chuỗi in mặc định có mã nhận diện của mảng để kết luận đã có từng Integer riêng.

### 3.2. Mảng nguyên thủy rỗng vẫn là một phần tử

`new int[0]` là một đối tượng mảng hợp lệ, có độ dài bằng 0. Khi nó được dùng làm một phần tử varargs, List ngoài vẫn có size bằng một.

Ngược lại, `new Integer[0]` có thể trực tiếp làm mảng tham số Integer của lời gọi tương ứng, nên List có size bằng 0. Đây là một cách kiểm tra rất rõ sự khác biệt giữa số ô trong nguồn và số phần tử ở tầng List.

### 3.3. Null có kiểu int[] và null có kiểu Integer[]

Biến missing trong ví dụ có kiểu `int[]` và giá trị null. Lời gọi tạo một List có một phần tử null ở vị trí dành cho `int[]`. Mảng varargs ngoài vẫn tồn tại và có một ô.

Ép null sang `Integer[]` lại truyền một mảng tham số null cho lời gọi đang nhận các phần tử Integer, nên gây NullPointerException. Muốn hiểu một ca null, phải xác định null nằm ở **tầng mảng tham số** hay **tầng phần tử**.

Không lấy một trường hợp null này để suy ra mọi lời gọi Arrays.asList với null đều có cùng kết quả. Kiểu của biểu thức tại nơi gọi ảnh hưởng đến cách varargs được áp dụng.

Hợp đồng mảng tham số và kích thước cố định được mô tả tại [Arrays.asList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)).

## 4. Trình biên dịch giúp phát hiện yêu cầu sai kiểu

Tệp dưới đây là **ca lỗi biên dịch chủ đích**, không phải chương trình để chạy bằng java. Lưu thành `RejectPrimitiveAsIntegerDemo.java` nếu muốn kiểm tra việc trình biên dịch từ chối phép gán.

```java
import java.util.Arrays;
import java.util.List;

public class RejectPrimitiveAsIntegerDemo {
    public static void main(String[] args) {
        int[] source = {4, 8, 15};
        List<Integer> values = Arrays.asList(source);
    }
}
```

Chỉ biên dịch để kiểm tra lỗi chủ đích:

```shell
javac --release 17 -encoding UTF-8 RejectPrimitiveAsIntegerDemo.java
```

Trình biên dịch từ chối vì không thể vừa đáp ứng phần tử Integer ở vế nhận vừa coi `int[]` đầu vào là các phần tử Integer. Kết quả của lời gọi không có quá trình tự chuyển từng số như yêu cầu của biến values.

Không có stdout của chương trình này vì bước biên dịch không thành công. Nội dung chi tiết của thông báo có thể khác giữa môi trường biên dịch; điều cần kiểm chứng là phép gán không hợp lệ.

Đổi biến nhận thành `List<int[]>` làm đúng kiểu của kết quả trong ví dụ, nhưng chưa đáp ứng yêu cầu “mỗi số là một phần tử”. Muốn đạt yêu cầu đó, cần đổi quá trình chuyển dữ liệu, không chỉ làm dòng mã biên dịch bằng cách đổi hoặc xóa thông tin kiểu.

## 5. Chuyển từng giá trị khi cần List<Integer>

Có thể sửa đúng hình dạng dữ liệu bằng một vòng lặp: lấy từng int từ nguồn rồi thêm vào một `List<Integer>`. Mỗi lần thêm áp dụng việc đóng gói phù hợp cho một giá trị.

Với stream, `Arrays.stream(intArray)` cung cấp IntStream, tức dãy các giá trị int của mảng. Gọi `boxed()` tạo dãy Integer tương ứng. Sau đó chọn cách thu kết quả theo quyền sửa cần có.

Lưu thành `PrimitiveBoxingChoicesDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

public class PrimitiveBoxingChoicesDemo {
    public static void main(String[] args) {
        int[] source = {4, 8, 15};
        List<Integer> manual = new ArrayList<>();
        for (int value : source) {
            manual.add(value);
        }

        List<Integer> snapshot = Arrays.stream(source).boxed().toList();
        ArrayList<Integer> editable = Arrays.stream(source)
                .boxed()
                .collect(Collectors.toCollection(ArrayList::new));
        List<Integer> fromScalars = Arrays.asList(4, 8, 15);
        Integer[] wrappers = {4, 8, 15};
        List<Integer> fromWrapperArray = Arrays.asList(wrappers);

        source[0] = 99;
        manual.add(16);
        editable.add(23);
        System.out.println("source=" + Arrays.toString(source));
        System.out.println("manual=" + manual);
        System.out.println("snapshot=" + snapshot);
        System.out.println("editable=" + editable);
        System.out.println("fromScalars=" + fromScalars);
        System.out.println("fromWrapperArray=" + fromWrapperArray);
        System.out.println("containsEight=" + snapshot.contains(8));
        try {
            snapshot.add(42);
        } catch (UnsupportedOperationException e) {
            System.out.println("snapshotAdd=UnsupportedOperationException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 PrimitiveBoxingChoicesDemo.java
java PrimitiveBoxingChoicesDemo
```

Stdout:

```text
source=[99, 8, 15]
manual=[4, 8, 15, 16]
snapshot=[4, 8, 15]
editable=[4, 8, 15, 23]
fromScalars=[4, 8, 15]
fromWrapperArray=[4, 8, 15]
containsEight=true
snapshotAdd=UnsupportedOperationException
```

Ba kết quả đầu được tạo bằng việc lấy từng giá trị từ source trước khi source đổi phần tử đầu thành 99:

| Kết quả | Cách tạo | Quyền sửa phần chứa |
| --- | --- | --- |
| `manual` | Vòng lặp thêm từng int vào ArrayList | Có thể thêm/xóa/thay phần tử |
| `snapshot` | Arrays.stream rồi boxed rồi Stream.toList | Không cho sửa List |
| `editable` | Stream và bộ thu tạo ArrayList cụ thể | Có thể thêm/xóa/thay phần tử |

Dữ liệu đã thu không theo lần gán 99 vào ô mảng về sau. Kết quả chứa các giá trị Integer được lấy lúc xử lý, không giữ source như một phần tử mảng. Vì đã có từng Integer ở tầng List, `contains(8)` trong snapshot trả true.

Manual được thêm 16 và editable được thêm 23 để kiểm chứng khả năng thay kích thước. Snapshot không cho thêm, nên ca cuối ném UnsupportedOperationException. Chuyển đúng kiểu phần tử và chọn đúng quyền sửa là hai quyết định cần làm cùng nhau.

`Stream.toList()` có từ Java 16 và trả List không cho sửa phần chứa. Các ví dụ này dùng Java 17. Nếu cần một ArrayList cụ thể, `Collectors.toCollection(ArrayList::new)` công bố rõ lựa chọn đó. Không dựa vào tên `Collectors.toList()` để mặc định một kiểu triển khai hay quyền sửa mà hợp đồng của nó không hứa.

Hai kết quả fromScalars và fromWrapperArray là các ca so sánh được chuẩn bị riêng trong chương trình. Truyền ba đối số int rời cho Arrays.asList cho phép Java đóng gói từng đối số. Truyền `Integer[]` phù hợp cho phép lấy từng Integer trong mảng. Hai khai báo này không là một phép ép kiểu biến `int[]` thành `Integer[]`.

List tạo bằng Arrays.asList trong hai ca so sánh vẫn có kích thước cố định. Việc nó chứa đúng Integer không tự làm nó trở thành ArrayList có thể thêm/xóa. Với `Integer[]`, nó còn là view dùng chung các ô của mảng ấy.

Các hợp đồng dùng ở đây: [IntStream.boxed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html#boxed()), [Stream.toList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()) và [Collectors.toCollection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toCollection(java.util.function.Supplier)).

## 6. Những cách thay lớp ngoài vẫn giữ một mảng ở bên trong

Một cách sửa thường thấy là bọc kết quả bằng `new ArrayList<>(...)`. Cách đó thay khả năng sửa của List ngoài nhưng không tự mở mảng thành từng số.

Tương tự, `List.of(source)` có thể tạo List chỉ đọc chứa một `int[]`, còn sao chép source trước khi gọi Arrays.asList có thể tạo một mảng độc lập nhưng vẫn giữ mảng ấy như một phần tử.

Lưu thành `PrimitiveOuterListDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class PrimitiveOuterListDemo {
    public static void main(String[] args) {
        int[] source = {2, 5};
        List<int[]> editableOuter = new ArrayList<>(Arrays.asList(source));
        List<int[]> readOnlyOuter = List.of(source);
        List<int[]> copiedArray = Arrays.asList(source.clone());

        source[0] = 9;
        System.out.println("editableOuterSize=" + editableOuter.size());
        System.out.println("readOnlyOuterSize=" + readOnlyOuter.size());
        System.out.println("editableElement="
                + Arrays.toString(editableOuter.get(0)));
        System.out.println("readOnlyElement="
                + Arrays.toString(readOnlyOuter.get(0)));
        System.out.println("copiedElement="
                + Arrays.toString(copiedArray.get(0)));

        editableOuter.add(new int[]{7, 8});
        System.out.println("afterAddingArray=" + editableOuter.size());
        readOnlyOuter.get(0)[1] = 11;
        System.out.println("sourceAfterElementEdit=" + Arrays.toString(source));
        try {
            readOnlyOuter.set(0, new int[]{0});
        } catch (UnsupportedOperationException e) {
            System.out.println("outerSet=UnsupportedOperationException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 PrimitiveOuterListDemo.java
java PrimitiveOuterListDemo
```

Stdout:

```text
editableOuterSize=1
readOnlyOuterSize=1
editableElement=[9, 5]
readOnlyElement=[9, 5]
copiedElement=[2, 5]
afterAddingArray=2
sourceAfterElementEdit=[9, 11]
outerSet=UnsupportedOperationException
```

EditableOuter bắt đầu có size bằng một. Thêm một mảng `{7, 8}` làm size thành hai: bây giờ có hai phần tử mảng, không có bốn số Integer ở tầng List. Đây là kết quả đúng nếu dữ liệu cần biểu diễn là các lô số.

ReadOnlyOuter cũng có một phần tử là source. Không thể set một phần tử List khác vào vị trí 0, nhưng vẫn có thể sửa ô số trong `int[]` đã lấy ra. Dòng sourceAfterElementEdit cho thấy sửa phần tử mảng qua đường đó đã tác động lên source.

CopiedArray chứa bản sao mảng với các ô số riêng nên giữ `[2, 5]` sau khi source đổi thành `[9, 5]`. Tuy vậy, List ngoài vẫn chỉ có một phần tử mảng. Việc tách trạng thái nguồn và việc đổi tầng dữ liệu là hai bài toán khác nhau.

| Thao tác chuẩn bị | Có thành List các Integer không? | Điều thật sự thay đổi |
| --- | --- | --- |
| Arrays.asList trên `int[]` | Không | Tạo List chứa mảng |
| ArrayList mới từ List ấy | Không | Phần chứa ngoài có thể thêm/xóa |
| List.of với `int[]` như một phần tử | Không | Phần chứa ngoài chỉ đọc |
| Sao chép `int[]` rồi tạo List chứa nó | Không | Mảng phần tử có các ô số riêng |
| Lấy từng int và đóng gói | Có | Mỗi số trở thành phần tử Integer |

Nếu yêu cầu là danh sách số, không dùng việc List ngoài đã có thể add làm bằng chứng rằng bẫy ban đầu đã được sửa. Kiểm tra cả size và kiểu của một phần tử.

Ngược lại, nếu mục tiêu là giữ một bộ sưu tập các mảng, không cần cố chuyển mọi thứ thành Integer. Hãy dùng kiểu `List<int[]>` có chủ đích và mô tả rõ việc mảng phần tử được chia sẻ hay được sao chép.

## 7. Bẫy cũng áp dụng cho các mảng nguyên thủy khác

Cùng nguyên tắc xảy ra với `byte[]`, `short[]`, `long[]`, `float[]`, `double[]`, `char[]` và `boolean[]`. Mỗi mảng ấy là một đối tượng có thể làm phần tử tham chiếu trong một List.

Không suy rằng vì Arrays.stream có một số cách nhận mảng nguyên thủy nên mọi kiểu nguyên thủy đều có cùng một lệnh stream trực tiếp. Trong Java 17, các phương thức chuyên biệt cho mảng nguyên thủy của Arrays.stream nhận `int[]`, `long[]` và `double[]`.

Với những kiểu còn lại, vòng lặp lấy từng giá trị là một cách rõ ràng, không cần giả định một chữ ký không tồn tại. Kiểu phần tử List cần dùng là kiểu bao tương ứng.

| Mảng nguồn | Phần tử trong List nếu truyền cả mảng cho asList | List các giá trị nếu chuyển từng ô |
| --- | --- | --- |
| `byte[]` | `byte[]` | Byte |
| `short[]` | `short[]` | Short |
| `int[]` | `int[]` | Integer |
| `long[]` | `long[]` | Long |
| `float[]` | `float[]` | Float |
| `double[]` | `double[]` | Double |
| `char[]` | `char[]` | Character |
| `boolean[]` | `boolean[]` | Boolean |

Lưu thành `OtherPrimitiveArraysDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class OtherPrimitiveArraysDemo {
    public static void main(String[] args) {
        boolean[] flags = {true, false};
        char[] letters = {'a', 'b'};
        float[] weights = {1.5f, 2.5f};
        System.out.println("booleanArrayListSize=" + Arrays.asList(flags).size());
        System.out.println("charArrayListSize=" + Arrays.asList(letters).size());
        System.out.println("floatArrayListSize=" + Arrays.asList(weights).size());

        List<Character> characters = new ArrayList<>();
        for (char value : letters) {
            characters.add(value);
        }
        List<Boolean> booleans = new ArrayList<>();
        for (boolean value : flags) {
            booleans.add(value);
        }
        System.out.println("characters=" + characters);
        System.out.println("booleans=" + booleans);
        System.out.println("longs="
                + Arrays.stream(new long[]{3L, 6L}).boxed().toList());
        System.out.println("doubles="
                + Arrays.stream(new double[]{1.5, 2.5}).boxed().toList());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 OtherPrimitiveArraysDemo.java
java OtherPrimitiveArraysDemo
```

Stdout:

```text
booleanArrayListSize=1
charArrayListSize=1
floatArrayListSize=1
characters=[a, b]
booleans=[true, false]
longs=[3, 6]
doubles=[1.5, 2.5]
```

Ba phép gọi asList đều cho size bằng một, bất kể mảng chứa hai giá trị. Các vòng lặp lại tạo List chứa từng Character hoặc Boolean, đúng với yêu cầu lấy giá trị ở từng ô.

Hai dòng long và double dùng những phương thức nhận mảng tương ứng của Arrays.stream, rồi đóng gói từng giá trị. Chúng không chứng minh rằng mọi mảng nguyên thủy đều tự chuyển theo cùng một chữ ký generic.

Xem các chữ ký được công bố của [Arrays.stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#stream(int%5B%5D)) khi chọn cách chuyển. Nếu chưa cần phép xử lý theo stream, một vòng lặp ngắn có thể thể hiện quá trình chuyển rất rõ.

## 8. Cách kiểm tra một kết quả chuyển đổi

Trước khi chọn cách sửa, hãy trả lời ba câu hỏi theo đúng thứ tự.

**Một phần tử của kết quả phải là gì?** Nếu câu trả lời là Integer, kiểm tra kiểu khai báo `List<Integer>` và cách tạo từng Integer. Nếu câu trả lời là một lô int, kiểu `List<int[]>` có thể là chủ đích đúng.

**Có bao nhiêu phần tử ở tầng ngoài?** Không dùng chiều dài của mảng phần tử để thay cho size của List. Đặc biệt, một `int[]` rỗng vẫn có thể nằm trong một List có một phần tử.

**Những đối tượng nào còn được chia sẻ?** List chứa mảng thường có thể giữ chính mảng nguồn. List chứa các Integer đã lấy từ từng ô là một hình dạng khác; việc nguồn thay ô số về sau không thay các giá trị đã thu.

| Dấu hiệu | Cách đọc đúng | Hướng xử lý khi cần từng số |
| --- | --- | --- |
| Size bằng một dù nguồn có nhiều số | List chứa một mảng | Duyệt từng giá trị hoặc dùng stream nguyên thủy thích hợp |
| Contains một số trả false | Tìm ở tầng List đang chứa mảng | Tạo `List<Integer>` hoặc tìm trực tiếp trong nguồn theo mục tiêu |
| Gán `List<Integer>` không biên dịch | Kiểu phần tử mong muốn khác kiểu từ lời gọi | Sửa quá trình chuyển đổi |
| Bọc bằng ArrayList vẫn có size một | Chỉ thay phần chứa ngoài | Lấy từng ô nguồn trước khi thêm |
| Clone mảng rồi asList vẫn có size một | Mảng đã riêng nhưng vẫn là một phần tử | Phân biệt độc lập trạng thái với đổi hình dạng dữ liệu |
| List chỉ đọc nhưng số trong mảng vẫn đổi được | Chỉ chặn sửa tầng List | Chọn ảnh chụp các giá trị hoặc sao chép mảng theo hợp đồng |
| Đổi sang var khiến không thấy lỗi gán | Kiểu được suy ra vẫn theo lời gọi | Kiểm tra kiểu thực tế và khai báo rõ ý định ở ranh giới API |

Không dùng kiểu thô hoặc ép kiểu để che việc T không đáp ứng yêu cầu. Các thao tác đó không chạy một vòng lặp chuyển int thành Integer. Một lỗi kiểu được phát hiện sớm thường giúp tìm đúng nguyên nhân hơn một kết quả bị hiểu sai sau khi đã truyền qua nhiều lớp.

Đối với dữ liệu null, trước hết quyết định chính sách của API. Các cách chuyển bằng vòng lặp hoặc Arrays.stream trong ví dụ giả định nguồn hợp lệ, không phải cam kết rằng mảng null tự chuyển thành List rỗng. List có một phần tử null của ca varargs cũng không đồng nghĩa với “không có số nào”.

Việc chuyển từng giá trị cần thời gian và bộ nhớ theo lượng dữ liệu kết quả. Nếu thuật toán chỉ cần xử lý số nguyên mà không cần giao diện `List<Integer>`, có thể giữ mảng nguyên thủy hoặc một luồng nguyên thủy phù hợp. Không cần thêm tầng kiểu bao chỉ để làm cho một lời gọi asList trông hợp lệ.

## 9. Thực hành có mục tiêu dữ liệu rõ ràng

### Bài 1: Ba số, một mảng

Tạo `int[]` có ba số và lấy kết quả Arrays.asList với kiểu `List<int[]>`. Dự đoán size, kiểu phần tử đầu và việc so sánh tham chiếu với nguồn.

Tiêu chí đạt: size bằng một, phần tử đầu là `int[]` và cùng tham chiếu với nguồn. Đếm ba ô trong mảng không đồng nghĩa có ba phần tử ở tầng List.

### Bài 2: Từng số là một phần tử

Từ cùng `int[]`, tạo ArrayList Integer bằng vòng lặp và một List bằng Arrays.stream rồi boxed.

Kiểm tra size bằng số ô nguồn, tìm được một số bằng contains, và việc thay một ô nguồn sau khi thu không đổi dữ liệu đã thu. Xác định thêm quyền add/remove của từng List theo cách tạo đã chọn.

### Bài 3: Bản sao ngoài chưa đổi kiểu phần tử

Tạo ArrayList từ Arrays.asList của `int[]`. Sau đó thêm một `int[]` khác vào List.

Tiêu chí đạt: List có hai mảng, không phải tập hợp các Integer của cả hai mảng. Giải thích được tại sao tạo phần chứa mới không tự trải các phần tử lồng.

### Bài 4: Nguồn rỗng

So sánh Arrays.asList của `int[]` rỗng với kết quả vòng lặp chuyển từng int từ mảng rỗng sang `List<Integer>`.

Một kết quả có một phần tử mảng; kết quả còn lại không có Integer nào. Hãy nêu rõ mình đang đếm ở tầng nào khi kiểm tra dữ liệu rỗng.

### Bài 5: Null có kiểu

Kiểm tra biến `int[]` mang null và biểu thức null được ép thành `Integer[]`. Trước khi chạy, mô tả mảng varargs ngoài trong từng trường hợp.

Tiêu chí đạt: giải thích được một bên có một phần tử null, một bên không có mảng tham số hợp lệ. Không thay lời giải bằng quy tắc chung “null luôn giống nhau”.

### Bài 6: Đổi kiểu nguyên thủy

Chọn `char[]` hoặc `boolean[]` và chuyển từng giá trị vào List kiểu bao tương ứng. So sánh size với việc gọi Arrays.asList trực tiếp trên cả mảng.

Tiêu chí đạt: chọn Character hoặc Boolean đúng với dữ liệu; không giả định Arrays.stream có cùng chữ ký trực tiếp cho mọi loại mảng nguyên thủy.

## 10. Các câu hỏi tự kiểm tra

1. **Vì sao asList của `int[]` có thể biên dịch?** Vì chính `int[]` là một đối tượng có kiểu tham chiếu có thể làm một phần tử generic.
2. **Vì sao nó không tự thành `List<Integer>`?** Không có phép đóng gói tự động toàn bộ `int[]` thành `Integer[]` hoặc một vòng lặp chuyển từng ô trong lời gọi đó.
3. **Một `int[]` rỗng tạo size ngoài bằng mấy?** Bằng một trong lời gọi đang coi mảng là một phần tử.
4. **Tìm một số bằng contains có tìm sâu vào mảng không?** Không. Contains làm việc với các phần tử của List ở tầng hiện tại.
5. **Cùng các số có làm hai mảng bằng nhau theo equals mặc định không?** Không. Dùng phép so sánh nội dung mảng phù hợp nếu đó là yêu cầu.
6. **Bọc ArrayList có sửa được hình dạng sai không?** Không. Nó có thể làm List ngoài thay kích thước được nhưng vẫn giữ phần tử mảng.
7. **Clone mảng có làm từng int thành Integer không?** Không. Nó tạo các ô số riêng cho một mảng khác.
8. **Cách chuyển sang `List<Integer>` rõ ràng là gì?** Lấy từng int rồi thêm vào List, hoặc dùng Arrays.stream trên `int[]` rồi boxed và thu kết quả.
9. **Stream.toList có cho thêm/xóa không?** Không. Trong Java 17, kết quả được công bố là List không cho sửa phần chứa.
10. **Khi nào `List<int[]>` là đúng?** Khi mỗi phần tử được chủ đích mô hình hóa là một mảng hoặc một lô số, với chính sách chia sẻ/sao chép rõ ràng.

