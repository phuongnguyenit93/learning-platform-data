# So sánh hợp đồng của `List.copyOf`, `new ArrayList` và `Collections.unmodifiableList` (Java 10+)

## 1. Ba API có ba mục đích khác nhau

Khi có một collection nguồn và muốn tạo `List` để sử dụng ở một nơi khác, Java cung cấp nhiều cách. Ba cách sau **không có cùng hợp đồng**:

```java
List<String> source = new ArrayList<>(List.of("An", "Binh"));

var editable = new ArrayList<>(source);
var view = Collections.unmodifiableList(source);
var snapshot = List.copyOf(source);
```

Đoạn trên dùng các lớp `List`, `ArrayList` và `Collections` thuộc `java.util`; các dòng đặt trong một phương thức là mã minh họa, chưa phải chương trình độc lập.

- `new ArrayList<>(source)`: tạo **một danh sách mới, cho phép chỉnh sửa** và chép các tham chiếu phần tử của nguồn vào đó theo thứ tự duyệt.
- `Collections.unmodifiableList(source)`: trả về **một view không cho sửa qua view** nhưng được **chống lưng bởi chính source**. Người giữ tham chiếu tới nguồn vẫn có thể sửa nó; thay đổi sẽ nhìn thấy qua view.
- `List.copyOf(source)`: trả về **một danh sách không thể sửa đổi**, có **snapshot các phần tử** tại thời điểm tạo theo thứ tự duyệt. Sửa nguồn sau đó không làm thay đổi cấu trúc/nội dung vị trí phần tử trong kết quả.

**Đừng đồng nhất “unmodifiable” với “snapshot”.** Một view không cho sửa trực tiếp có thể vẫn thay đổi vì dữ liệu nền thay đổi. Cũng đừng đồng nhất “snapshot” với “deep copy”: cả `new ArrayList<>(source)` và `List.copyOf(source)` giữ **tham chiếu tới phần tử**, không sao chép sâu mọi đối tượng.

`List.copyOf` được giới thiệu trong Java 10 và tiếp tục là API hiện hành. `new ArrayList<>(Collection)` và `Collections.unmodifiableList` cũng là API hiện hành, không phải cú pháp hay thư viện bị loại bỏ.

## 2. Bảng so sánh hợp đồng

| Thuộc tính | `new ArrayList<>(source)` | `Collections.unmodifiableList(source)` | `List.copyOf(source)` |
| --- | --- | --- | --- |
| Loại kết quả | Một `ArrayList` mới | Một view kiểu `List` không cho sửa trực tiếp | `List` không thể sửa đổi |
| Thêm/xóa/đổi phần tử qua **kết quả** | Được | Không; các thao tác sửa ném `UnsupportedOperationException` | Không; các thao tác sửa ném `UnsupportedOperationException` |
| Cấu trúc kết quả đổi khi sửa nguồn sau lúc tạo? | Không | **Có**, vì view dựa trên nguồn | **Không**, vì snapshot |
| Chấp nhận phần tử `null` trong nguồn? | Có | Có, nếu nguồn cho phép `null` | **Không**; ném `NullPointerException` |
| Chấp nhận chính nguồn là `null`? | Không; ném `NullPointerException` | Không; ném `NullPointerException` | Không; ném `NullPointerException` |
| Sao chép sâu đối tượng phần tử? | Không | Không; dùng cùng nguồn | Không |
| Giữ thứ tự phần tử? | Theo thứ tự iterator của nguồn lúc tạo | Theo thứ tự được thể hiện ở nguồn hiện tại | Theo thứ tự iterator của nguồn lúc tạo |
| Có thể dựa vào việc mỗi lần gọi tạo identity khác? | Đối tượng `new ArrayList` là instance mới | Không nên dùng view làm cơ chế nhận diện/khóa thay thế | **Không**; instance value-based, có thể tái sử dụng |
| Mục đích chính | Cần bản sao **có thể sửa** | Muốn công khai một **góc nhìn chỉ đọc, cập nhật theo nguồn** | Muốn **snapshot không sửa được**, độc lập thay đổi cấu trúc của nguồn |

Phân biệt **khả năng sửa qua tham chiếu trả về** với **khả năng thay đổi do tác động bên ngoài** là mấu chốt của chủ đề này.

## 3. `new ArrayList<>(source)`: bản sao cấu trúc độc lập và sửa được

Constructor `ArrayList(Collection<? extends E>)` tạo một danh sách có các phần tử theo thứ tự mà iterator của nguồn cung cấp. Đây là một object `ArrayList` mới, tách khỏi cấu trúc danh sách ban đầu:

```java
var source = new ArrayList<>(List.of("A", "B"));
var copy = new ArrayList<>(source);

source.set(0, "X");  // source: [X, B]
source.add("C");     // source: [X, B, C]
copy.add("D");       // copy: [A, B, D]
```

Kết quả sau ba thao tác là:

```text
source = [X, B, C]
copy   = [A, B, D]
```

Những dòng `source = ...` ở trên là cách **trình bày trạng thái**, không phải output in ra từ đoạn Java trước đó. Constructor chỉ sao chép tập tham chiếu phần tử ở thời điểm gọi; sửa `source` không thay đổi cấu trúc `copy` và ngược lại.

**Hợp đồng quan trọng:**

- Kết quả có thể `add`, `remove`, `set`, `clear` và thực hiện các thao tác sửa hợp lệ khác.
- `ArrayList` cho phép phần tử `null`. Constructor `new ArrayList<>(source)` chỉ từ chối khi chính collection nguồn là `null`.
- Đây là **shallow copy**: nếu phần tử là một object mutable, cả nguồn lẫn bản sao đều có thể cùng tham chiếu đến object đó.
- `ArrayList` không tự đồng bộ hóa các thao tác cho nhiều luồng; cần thiết kế concurrency riêng nếu cùng một bản sao có thể bị sửa đồng thời.

Chọn constructor này khi cần **làm việc trên bản sao**, ví dụ sắp xếp, loại phần tử hoặc bổ sung phần tử mà không ảnh hưởng danh sách ban đầu.

## 4. `Collections.unmodifiableList(source)`: view chỉ đọc nhưng *live*

`Collections.unmodifiableList(source)` tạo một **unmodifiable view** của danh sách được truyền vào. Người dùng view không thể sửa danh sách thông qua view:

```java
var source = new ArrayList<>(List.of("A", "B"));
var view = Collections.unmodifiableList(source);

// view.add("C");  // chạy sẽ ném UnsupportedOperationException
// view.set(0, "X"); // cũng ném UnsupportedOperationException
```

Tuy nhiên, tham chiếu `source` vẫn có thể sửa:

```java
source.set(0, "X");
source.add("C");
System.out.println(view); // [X, B, C]
```

**Cốt lõi:** view chỉ cấm thay đổi **qua chính view**. Nó **không khóa**, **không đóng băng**, **không ngăn** những người giữ `source` sửa backing list. Vì vậy, `view` theo dõi nội dung hiện tại của `source`.

Việc gọi `Collections.unmodifiableList` là hữu ích khi **cố ý công khai dữ liệu đang cập nhật** nhưng không muốn caller sửa trực tiếp. Ví dụ, một lớp có thể trả ra view của danh sách nội bộ và chỉ cho phép thay đổi bằng các phương thức quản lý được kiểm soát. Tuy nhiên, caller vẫn quan sát thấy trạng thái mới, và nếu nhiều luồng cùng truy cập thì cần cơ chế đồng bộ/công bố phù hợp.

**Không xem unmodifiable view như snapshot:** lấy view tại thời điểm T1 không bảo đảm nó giữ nội dung T1 khi backing list đổi ở T2.

## 5. `List.copyOf(source)`: snapshot không sửa và không chứa `null`

`List.copyOf(Collection<? extends E>)` trả về một `List` không thể sửa đổi với các phần tử được duyệt từ collection nguồn ở thời điểm gọi:

```java
var source = new ArrayList<>(List.of("A", "B"));
var snapshot = List.copyOf(source);

source.set(0, "X");
source.add("C");

System.out.println(source);   // [X, B, C]
System.out.println(snapshot); // [A, B]
```

Không thể thay `snapshot` bằng cách gọi `add`, `remove` hoặc `set` trên nó. Mặt khác, sửa cấu trúc `source` sau khi tạo `snapshot` cũng không làm bản snapshot đổi.

Những điều phải nhớ về hợp đồng:

1. **Không có phần tử `null`:** nếu collection nguồn chứa một hay nhiều phần tử `null`, gọi `List.copyOf(source)` ném `NullPointerException`.
2. **Không nhận collection `null`:** `List.copyOf(null)` ném `NullPointerException`.
3. **Không sửa được:** các thao tác mutator trên kết quả ném `UnsupportedOperationException`.
4. **Giữ các phần tử theo thứ tự duyệt của nguồn:** với List nguồn, thứ tự này chính là thứ tự List; các phần tử trùng nhau vẫn được giữ lại.
5. **Không tự sao chép sâu phần tử:** các object phần tử có thể tiếp tục bị sửa qua tham chiếu khác.
6. **Value-based:** không đặt logic lên identity của instance trả về; factory có thể tạo object mới hoặc tái sử dụng object có sẵn.

Đặc biệt, nếu nguồn đã là một **unmodifiable List** phù hợp, implementation của `copyOf` **thường có thể tái sử dụng** cùng instance, không cần tạo một bản sao vật lý nữa. Do đó, gọi `copyOf` không hứa sẽ sinh ra object khác và không nên kiểm tra tính đúng đắn qua `original == snapshot`.

**Quan trọng:** khả năng tái sử dụng instance không làm mất hợp đồng snapshot. Nếu đầu vào là một **unmodifiable view vẫn phản ánh thay đổi của backing list**, kết quả `List.copyOf(view)` vẫn phải đáp ứng quy tắc **không phản ánh thay đổi sau đó của nguồn**. Không được suy luận “vì đầu vào không cho sửa qua view nên chắc chắn copyOf giữ nguyên view đó”.

## 6. Thử thay đổi nguồn: ba kết quả khác nhau

Giả sử dữ liệu ban đầu:

```java
var source = new ArrayList<>(List.of("An", "Binh"));
var editable = new ArrayList<>(source);
var view = Collections.unmodifiableList(source);
var snapshot = List.copyOf(source);

source.set(0, "Chi");
source.add("Dung");
editable.add("Em");
```

Sau khi thực hiện:

| Tham chiếu | Nội dung | Vì sao? |
| --- | --- | --- |
| `source` | `[Chi, Binh, Dung]` | Đã sửa trực tiếp danh sách nguồn. |
| `editable` | `[An, Binh, Em]` | Bản sao tách cấu trúc khỏi nguồn, được thêm `Em` riêng. |
| `view` | `[Chi, Binh, Dung]` | View đang nhìn trực tiếp vào backing `source`. |
| `snapshot` | `[An, Binh]` | `List.copyOf` giữ trạng thái ở lúc tạo. |

**Hành động nào gây lỗi?**

```java
view.add("X");      // UnsupportedOperationException khi chạy
snapshot.add("X");  // UnsupportedOperationException khi chạy
editable.add("X");  // hợp lệ
```

Java cho phép **biên dịch** cả ba lời gọi vì kiểu khai báo là `List` hoặc `ArrayList` có phương thức `add`. Với hai đối tượng unmodifiable, hợp đồng runtime của implementation mới quyết định việc ném ngoại lệ. Đừng đánh đồng việc biên dịch được `add` với việc một List cụ thể cho phép sửa.

## 7. `null`: trường hợp chọn API làm thay đổi kết quả

`ArrayList` cho phép phần tử `null`, và một unmodifiable view sẽ thể hiện đúng nội dung đó nếu backing chứa `null`. `List.copyOf` thì chủ động từ chối:

```java
var source = new ArrayList<String>();
source.add("A");
source.add(null);

var copy = new ArrayList<>(source);              // [A, null]
var view = Collections.unmodifiableList(source); // [A, null]
// var snapshot = List.copyOf(source);           // NullPointerException
```

Trường hợp này rất quan trọng khi nhận dữ liệu từ một API có thể chứa `null`: đổi từ `new ArrayList<>(source)` sang `List.copyOf(source)` không chỉ thay **khả năng sửa**, mà còn đổi **hợp đồng chấp nhận dữ liệu**.

Có hai hướng xử lý hợp lệ tùy nghiệp vụ:

- Nếu `null` là dữ liệu không hợp lệ: lọc, chuẩn hóa hoặc báo lỗi đầu vào trước khi tạo snapshot, rồi dùng `List.copyOf`.
- Nếu `null` mang ý nghĩa thực sự và phải được giữ lại: cân nhắc một cấu trúc/hợp đồng khác. Chẳng hạn `Collections.unmodifiableList(new ArrayList<>(source))` có thể tạo **view không sửa** trên một bản sao có chứa `null`, miễn là backing copy không bị sửa/lộ qua đường khác. Đây không phải là instance `List.copyOf`, và không có cùng quy định value-based.

Không nên âm thầm xóa hết `null` chỉ để dùng được `List.copyOf` nếu nghiệp vụ cần phân biệt giữa “không có phần tử” và “có phần tử mang giá trị null”.

## 8. Cả bản sao và snapshot đều nông: phần tử mutable vẫn thay đổi

Sự độc lập của **cấu trúc danh sách** không bảo đảm trạng thái **đối tượng phần tử** độc lập.

```java
var builder = new StringBuilder("draft");
var source = new ArrayList<StringBuilder>();
source.add(builder);

var editable = new ArrayList<>(source);
var snapshot = List.copyOf(source);
var view = Collections.unmodifiableList(source);

builder.append("-done");

System.out.println(editable); // [draft-done]
System.out.println(snapshot); // [draft-done]
System.out.println(view);     // [draft-done]
```

Ở đây các danh sách đều chứa **cùng tham chiếu** đến một `StringBuilder`. Không có thao tác `add` hoặc `set` trên `snapshot`; ta chỉ sửa object phần tử từ bên ngoài. Vì vậy danh sách “không thể sửa” vẫn có thể **trông như thay đổi** khi in ra.

Muốn một snapshot **bất biến sâu theo ý nghĩa nghiệp vụ**, phải làm cho các phần tử cũng bất biến hoặc tạo bản sao phần tử theo quy tắc riêng trước khi đưa vào list. `List.copyOf` không thay thế việc thiết kế immutable value object.

Với `String`, `Integer` và những kiểu bất biến thông dụng khác, việc giữ chung tham chiếu phần tử thường không gây vấn đề này. Nhưng cần kiểm tra bản chất của **từng kiểu phần tử**, không đánh giá tính bất biến chỉ dựa vào container.

## 9. `List.copyOf(Collections.unmodifiableList(source))` không phải live view

Vì view không cho sửa trực tiếp, có người nhầm rằng gọi `copyOf` lên nó sẽ giữ nguyên việc phản ánh nguồn:

```java
var source = new ArrayList<>(List.of("A", "B"));
var view = Collections.unmodifiableList(source);
var snapshot = List.copyOf(view);

source.add("C");

System.out.println(view);     // [A, B, C]
System.out.println(snapshot); // [A, B]
```

`List.copyOf` có **hợp đồng snapshot độc lập khỏi sửa đổi về sau ở collection đầu vào**, kể cả collection đó là unmodifiable view. Một lớp bao ngoài không cho phép sửa trực tiếp **không đồng nghĩa backing list không còn thay đổi**.

So sánh với:

```java
var first = List.of("A", "B");
var second = List.copyOf(first);
// Không dựa vào first == second để kiểm tra chương trình.
```

Với `List.of`, nguồn vốn đã là unmodifiable value-based list và có thể được reuse. Nhưng sự tái sử dụng này là **lựa chọn implementation**, không phải một cam kết identity để ứng dụng phụ thuộc vào.

**Quy tắc thiết kế:** dùng `List.copyOf` vì **ngữ nghĩa bản chụp không sửa được**, không phải vì kỳ vọng “luôn copy mới” hoặc “luôn cùng object”.

## 10. Khi nào dùng `Collections.unmodifiableList(new ArrayList<>(source))`?

Đôi khi yêu cầu vừa **không sửa qua kết quả**, vừa **không phản ánh sửa đổi sau đó của nguồn**, nhưng dữ liệu **có thể chứa `null`**:

```java
var source = new ArrayList<String>();
source.add("A");
source.add(null);

List<String> snapshotView =
        Collections.unmodifiableList(new ArrayList<>(source));
```

Cách này tạo một `ArrayList` mới rồi trả về view không sửa trực tiếp trên bản sao đó. Nếu không giữ/lộ tham chiếu tới backing copy cho mã khác, phần **cấu trúc list** không bị bên ngoài sửa qua view. Các phần tử vẫn là shallow references; `null` vẫn được giữ lại.

Điểm khác với `List.copyOf`:

- Có thể chứa `null` theo hợp đồng của `ArrayList`.
- Đây là **wrapper view** trên một backing list modifiable, không phải một `List.copyOf` value-based.
- Có thêm lớp bao ngoài và một bản sao cấu trúc; không thể khẳng định chi phí luôn tốt hơn hay xấu hơn `List.copyOf` mà không dựa vào ngữ cảnh và benchmark.
- Nếu vô tình giữ và công khai tham chiếu tới backing copy, snapshotView lại có thể đổi theo backing ấy.

Đây vẫn là cách dùng API hiện hành, không phải một giải pháp bị legacy. Nhưng khi **nguồn không chứa `null`**, muốn kết quả **không thể sửa và độc lập khỏi nguồn**, `List.copyOf(source)` thường diễn đạt ý định ngắn gọn, rõ nhất.

## 11. Sự khác biệt về danh tính, `equals` và chia sẻ giữa nhiều luồng

Ba danh sách có thể cùng nội dung mà vẫn có hợp đồng identity khác nhau:

```java
var source = new ArrayList<>(List.of("A", "B"));
var copy = new ArrayList<>(source);
var view = Collections.unmodifiableList(source);
var snapshot = List.copyOf(source);

System.out.println(copy.equals(view));     // true
System.out.println(view.equals(snapshot)); // true
```

`List.equals` so sánh **các phần tử theo thứ tự và theo giá trị**. `equals` là cách phù hợp để so sánh **nội dung**.

Đối với `List.copyOf`, đặc tả gọi kết quả là **value-based**:

- Không dùng kết quả làm monitor trong `synchronized(snapshot)`.
- Không phụ thuộc vào `==` hoặc `System.identityHashCode(snapshot)` để quản lý bản sắc nghiệp vụ.
- Không mặc định mỗi lần `List.copyOf` trả về instance riêng; factory có quyền tái sử dụng.

Đối với concurrency:

- `new ArrayList<>(source)` tạo list có thể sửa nhưng **không tự thread-safe**.
- `Collections.unmodifiableList(source)` **không làm backing source thread-safe**. Nếu source bị sửa đồng thời trong lúc đọc/duyệt view mà không có phối hợp thích hợp, có thể gặp race condition, trạng thái không nhất quán hoặc ngoại lệ.
- `List.copyOf(source)` tránh được những thay đổi **cấu trúc list** sau khi copy, nhưng việc **tạo snapshot từ một nguồn đang bị sửa đồng thời** phải được phối hợp phù hợp. Nó không phải một giao dịch/ảnh chụp nguyên tử của một backing list bất kỳ.
- Không API nào tự biến **các đối tượng phần tử mutable** thành thread-safe. Sự an toàn khi chia sẻ còn phụ thuộc vào cách công bố tham chiếu và tính bất biến của phần tử.

Nếu cần snapshot cấu hình nhiều luồng, thông thường nên tạo snapshot từ nguồn đã được phối hợp cập nhật, sau đó **công bố an toàn** (ví dụ qua trường `volatile` hoặc một cấu trúc có cơ chế đồng bộ thích hợp).

## 12. Ví dụ đầy đủ chạy trên Java 17+

Lưu chương trình sau vào tệp `CopyContractDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class CopyContractDemo {

    static void showFailure(String name, Runnable action) {
        try {
            action.run();
            System.out.println(name + "=none");
        } catch (UnsupportedOperationException | NullPointerException ex) {
            System.out.println(name + "=" + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        var source = new ArrayList<String>();
        source.add("An");
        source.add("Binh");

        var mutableCopy = new ArrayList<>(source);
        var liveView = Collections.unmodifiableList(source);
        var snapshot = List.copyOf(source);

        source.set(0, "Chi");
        source.add("Dung");
        mutableCopy.add("Em");

        System.out.println("source=" + source);
        System.out.println("mutableCopy=" + mutableCopy);
        System.out.println("liveView=" + liveView);
        System.out.println("snapshot=" + snapshot);

        showFailure("view.add", () -> liveView.add("X"));
        showFailure("snapshot.add", () -> snapshot.add("X"));

        var withNull = new ArrayList<String>(Arrays.asList("A", null));
        var nullableCopy = new ArrayList<>(withNull);
        var nullableView = Collections.unmodifiableList(withNull);
        System.out.println("nullableCopy=" + nullableCopy);
        System.out.println("nullableView=" + nullableView);
        showFailure("copyOf.null", () -> List.copyOf(withNull));

        var element = new StringBuilder("draft");
        var sourceElements = new ArrayList<StringBuilder>();
        sourceElements.add(element);
        var shallowSnapshot = List.copyOf(sourceElements);
        element.append("-done");
        System.out.println("shallowSnapshot=" + shallowSnapshot);

        var copyOfView = List.copyOf(liveView);
        source.add("Giap");
        System.out.println("view.after=" + liveView);
        System.out.println("copyOfView.after=" + copyOfView);
    }
}
```

Lệnh chạy:

```bash
javac CopyContractDemo.java
java CopyContractDemo
```

Đầu ra **chính xác**:

```text
source=[Chi, Binh, Dung]
mutableCopy=[An, Binh, Em]
liveView=[Chi, Binh, Dung]
snapshot=[An, Binh]
view.add=UnsupportedOperationException
snapshot.add=UnsupportedOperationException
nullableCopy=[A, null]
nullableView=[A, null]
copyOf.null=NullPointerException
shallowSnapshot=[draft-done]
view.after=[Chi, Binh, Dung, Giap]
copyOfView.after=[Chi, Binh, Dung]
```

Giải thích lần lượt:

1. `source` bị thay phần tử đầu và thêm `Dung`, nên `liveView` quan sát cùng nội dung mới.
2. `mutableCopy` giữ `An`/`Binh` từ lúc tạo và được thêm `Em` riêng, không phản ánh thay đổi cấu trúc của `source`.
3. `snapshot` giữ đúng `[An, Binh]` dù source đổi.
4. Hai lời gọi `add` qua `liveView` và `snapshot` đều ném `UnsupportedOperationException`.
5. `ArrayList` và unmodifiable view giữ `null`, nhưng `List.copyOf` từ chối `null` bằng `NullPointerException`.
6. Phần tử `StringBuilder` chung thay đổi làm cả snapshot chỉ đọc trông như đổi nội dung; nó không phải deep copy.
7. `copyOfView` giữ `[Chi, Binh, Dung]` dù sau đó `source` thêm `Giap`; chứng tỏ gọi `copyOf` trên view vẫn cần tuân thủ hợp đồng snapshot.

Ví dụ dùng `var` ở vị trí biến cục bộ, phù hợp từ Java 10; dùng `List.copyOf` cũng từ Java 10. Không dùng tính năng thử nghiệm, API lỗi thời hay phụ thuộc identity không được bảo đảm.

## 13. Chọn API theo nhu cầu thực tế

| Nhu cầu | Lựa chọn khuyến nghị | Lý do |
| --- | --- | --- |
| Cần danh sách riêng để thêm, xóa, sắp xếp | `new ArrayList<>(source)` | Bản sao cấu trúc độc lập, có thể sửa |
| Cần caller không sửa trực tiếp nhưng quan sát dữ liệu thay đổi ở backing | `Collections.unmodifiableList(source)` | View live trên nguồn |
| Cần xuất một bản chụp chỉ đọc, nguồn có thể thay đổi về sau | `List.copyOf(source)` | Unmodifiable snapshot; không cho `null` |
| Cần snapshot chỉ đọc nhưng phải giữ `null` | `Collections.unmodifiableList(new ArrayList<>(source))` | Copy cấu trúc rồi bao view, miễn backing copy không bị lộ |
| Cần snapshot bất biến sâu cho dữ liệu mutable | Sao chép/chuyển phần tử thành giá trị bất biến rồi dùng `List.copyOf` | Ba API trên không tự deep copy |
| Cần collection chỉ đọc được chia sẻ cho nhiều luồng | Snapshot phù hợp + phần tử an toàn + safe publication | “Không sửa cấu trúc” không thay thế thiết kế concurrency |

Khi thiết kế API của một lớp:

```java
final class Catalog {
    private final List<String> items = new ArrayList<>();

    void add(String item) {
        items.add(item);
    }

    List<String> snapshot() {
        return List.copyOf(items);
    }

    List<String> liveView() {
        return Collections.unmodifiableList(items);
    }
}
```

Đây là **lớp minh họa**, cần import `java.util.List`, `ArrayList`, `Collections` và không được dùng đồng thời từ nhiều luồng nếu chưa có cơ chế đồng bộ. `snapshot()` cố ý trả dữ liệu cố định theo thời điểm gọi; `liveView()` cố ý trả góc nhìn phản ánh các lệnh `add` sau đó. Tên phương thức và tài liệu API nên diễn đạt **khác biệt này**, vì người gọi có thể phụ thuộc mạnh vào nó.

## 14. Các lỗi phổ biến

| Hiểu sai | Điều đúng |
| --- | --- |
| “`Collections.unmodifiableList(source)` đóng băng `source`.” | Không, nó chỉ chặn sửa qua view. Bên nắm `source` vẫn sửa được. |
| “`List.copyOf(source)` luôn tạo object mới.” | Không có cam kết identity; có thể tái sử dụng unmodifiable list phù hợp. |
| “`new ArrayList<>(source)` và `List.copyOf(source)` có cùng quyền sửa.” | `ArrayList` sửa được; kết quả `copyOf` không sửa được. |
| “`List.copyOf` nhận được list có `null` vì List nói chung nhận null.” | Không: `List.copyOf` ném `NullPointerException` nếu nguồn có `null`. |
| “Nếu `snapshot` không sửa được, các đối tượng bên trong cũng bất biến.” | Sai: snapshot là shallow; phần tử mutable có thể đổi qua tham chiếu khác. |
| “Đầu vào là unmodifiable view thì `List.copyOf` trở thành live view.” | Sai: kết quả `List.copyOf` không phản ánh thay đổi tiếp theo của collection nguồn. |
| “Thấy `copyOf` bằng nhau theo `equals` nên có cùng monitor.” | `equals` so sánh giá trị; kết quả `copyOf` là value-based, không dùng cho synchronization theo identity. |
| “View chỉ đọc là thread-safe.” | View không tự đồng bộ việc truy cập backing list hoặc phần tử mutable. |

## 15. Tự kiểm tra

Giả sử các import cần thiết đã có:

```java
var source = new ArrayList<>(List.of("A", "B"));
var a = new ArrayList<>(source);
var b = Collections.unmodifiableList(source);
var c = List.copyOf(source);

source.set(1, "X");
a.add("C");
```

**Câu 1:** Nội dung của `a`, `b`, `c` là gì?

**Đáp án:** `a` là `[A, B, C]`, `b` là `[A, X]`, `c` là `[A, B]`. `a` tự quản lý cấu trúc, `b` phản ánh `source`, `c` giữ snapshot.

**Câu 2:** Nếu gọi `b.clear()` hoặc `c.set(0, "Y")` thì sao?

**Đáp án:** Hai thao tác ném `UnsupportedOperationException` vì cả hai kết quả không cho sửa qua tham chiếu trả về.

**Câu 3:** Nếu `source` chứa một `null` rồi tạo thêm `new ArrayList<>(source)`, `Collections.unmodifiableList(source)`, `List.copyOf(source)` thì sao?

**Đáp án:** Hai API đầu giữ `null`; `List.copyOf(source)` ném `NullPointerException`.

**Câu 4:** Vì sao `List.copyOf(Collections.unmodifiableList(source))` vẫn không phải live view?

**Đáp án:** Vì `copyOf` có hợp đồng không phản ánh sửa đổi sau đó ở collection đầu vào. Unmodifiable view có thể thay đổi qua backing, nhưng kết quả `copyOf` phải giữ các phần tử ở thời điểm tạo.

**Câu 5:** Nếu một phần tử là `StringBuilder` rồi nội dung của nó bị sửa, bản sao và snapshot có đổi phần tử hiển thị không?

**Đáp án:** Có thể có. Các API nêu trên không deep copy `StringBuilder`; danh sách chứa cùng tham chiếu. Muốn dữ liệu bất biến sâu, phải dùng phần tử bất biến hoặc tự sao chép phần tử.

## Kết luận

**Ba hợp đồng phải được lựa chọn theo mục tiêu:**

- `new ArrayList<>(source)` — **copy độc lập cấu trúc, cho sửa**.
- `Collections.unmodifiableList(source)` — **view không sửa trực tiếp, nhưng live theo backing**.
- `List.copyOf(source)` — **snapshot không sửa được, không chứa `null`, không phụ thuộc thay đổi cấu trúc về sau của nguồn**.

Cả ba đều không thực hiện deep copy các phần tử. Muốn mã đáng tin cậy, hãy mô tả rõ liệu API trả về **bản sao để sửa**, **view chỉ đọc đang thay đổi**, hay **snapshot chỉ đọc**. Kiểm tra thêm chính sách `null`, vấn đề tham chiếu phần tử mutable và sự an toàn khi chia sẻ giữa các luồng.

## Tài liệu tham khảo chính thức

- [Java SE 26 — `List.copyOf` và hợp đồng Unmodifiable Lists](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): quy định snapshot, `null`, value-based và khả năng reuse instance.
- [Java SE 26 — `ArrayList(Collection)`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ArrayList.html#%3Cinit%3E(java.util.Collection)): tạo list mới theo thứ tự duyệt, cho phép `null` và sửa nội dung.
- [Java SE 26 — `Collections.unmodifiableList`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): view chỉ đọc trên backing list.
- [Oracle Java Core Libraries — Creating Unmodifiable Lists, Sets, and Maps](https://docs.oracle.com/en/java/javase/26/core/creating-immutable-lists-sets-and-maps.html): so sánh unmodifiable view và snapshot từ `copyOf`.
