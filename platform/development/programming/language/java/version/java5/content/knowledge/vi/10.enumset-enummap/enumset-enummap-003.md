# Sao chép và lấy phần bù của tập enum

## 1. Hai thao tác cùng cần biết kiểu enum

`EnumSet<E>` biểu diễn một tập các hằng của đúng một kiểu enum `E`. Khi làm việc với nó, hai nhu cầu thường gặp là tạo một tập độc lập có cùng phần tử và tìm những hằng chưa có trong tập hiện tại.

Sao chép giữ lại các phần tử đang được chọn. Lấy phần bù tạo tập chứa các hằng còn lại trong **toàn bộ kiểu enum** đó.

Ví dụ với:

```java
enum Capability {
    READ, WRITE, EXPORT, AUDIT
}
```

Nếu tập đang chọn là `[READ, WRITE]`, một bản sao cũng ban đầu chứa `[READ, WRITE]`; phần bù theo toàn bộ `Capability` là `[EXPORT, AUDIT]`.

Cả hai kết quả đều là những đối tượng tập mới, không phải những tên khác của tập nguồn. Các API này vẫn áp dụng trong Java hiện hành; chương trình của bài chạy bằng JDK 17 trở lên.

## 2. Phân biệt gán tham chiếu với tạo bản sao

```java
EnumSet<Capability> selected = EnumSet.of(Capability.READ);
EnumSet<Capability> alias = selected;
alias.add(Capability.WRITE);
```

Biến `alias` và `selected` tham chiếu tới cùng một tập. Thêm qua `alias` cũng được thấy khi đọc qua `selected`. Dòng gán không tạo bản sao.

Nếu cần giữ một tập lựa chọn độc lập:

```java
EnumSet<Capability> copied = EnumSet.copyOf(selected);
copied.remove(Capability.WRITE);
```

Xóa phần tử khỏi `copied` không xóa khỏi `selected`. Việc thêm hoặc xóa sau đó ở tập nguồn cũng không tự phản ánh sang bản sao.

Bản sao vẫn có thể sửa đổi như một `EnumSet` thông thường. Sao chép không tự tạo tính bất biến hoặc một tập không cho sửa.

Các phần tử enum vẫn là những hằng enum tương ứng; không tạo bản sao của từng hằng. Điều được sao chép ở đây là trạng thái thành viên của tập. Nếu enum được thiết kế có trạng thái sửa đổi được, sao chép tập không tự cô lập trạng thái bên trong các hằng đó.

## 3. Hai dạng copyOf và bẫy collection rỗng

### 3.1. copyOf nhận EnumSet

```java
EnumSet<Capability> empty = EnumSet.noneOf(Capability.class);
EnumSet<Capability> copied = EnumSet.copyOf(empty);
```

Dù không chứa phần tử, `empty` vẫn mang thông tin kiểu phần tử là `Capability`, nên bản sao rỗng vẫn được tạo bình thường và có đúng kiểu enum đó.

Dạng [EnumSet.copyOf(EnumSet)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/EnumSet.html#copyOf(java.util.EnumSet)) tạo tập mới có cùng kiểu phần tử và ban đầu chứa cùng các phần tử.

### 3.2. copyOf nhận một Collection

```java
List<Capability> source = List.of(Capability.EXPORT, Capability.READ);
EnumSet<Capability> copied = EnumSet.copyOf(source);
```

Với một collection không phải `EnumSet`, nguồn phải có ít nhất một phần tử để xác định kiểu enum cần dùng. Nếu nguồn là một `List<Capability>` rỗng, `EnumSet.copyOf(source)` ném `IllegalArgumentException`.

Tên kiểu generic mà ta thấy ở mã nguồn không tự cung cấp cho API một đối tượng `Class<Capability>` để dùng lúc chạy. Không thể dựa vào một phần tử đầu tiên khi danh sách không có phần tử nào.

Điểm cần đọc đúng là **kiểu đối tượng nguồn**, không chỉ kiểu biến tham chiếu. Nếu biến có kiểu `Collection<Capability>` nhưng đối tượng thật là một `EnumSet<Capability>` rỗng, `copyOf(Collection)` vẫn nhận ra đó là `EnumSet` và xử lý như sao chép `EnumSet`.

```java
Collection<Capability> source = EnumSet.noneOf(Capability.class);
EnumSet<Capability> copied = EnumSet.copyOf(source); // Hợp lệ
```

Ngược lại, một wrapper collection rỗng không phải chính một đối tượng `EnumSet` không tự bảo đảm giữ được đường suy ra kiểu ấy cho `copyOf`. Khi nguồn có thể rỗng và chỉ công bố một hợp đồng collection tổng quát, cung cấp kiểu enum rõ ràng là cách đáng tin cậy.

Hợp đồng và ngoại lệ được mô tả tại [EnumSet.copyOf(Collection)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/EnumSet.html#copyOf(java.util.Collection)).

### 3.3. Khi nguồn có thể là collection rỗng bất kỳ

```java
static <E extends Enum<E>> EnumSet<E> copyWithType(
        Class<E> elementType, Collection<? extends E> source) {
    EnumSet<E> result = EnumSet.noneOf(elementType);
    result.addAll(source);
    return result;
}
```

Hàm tạo tập rỗng theo kiểu đã cung cấp rồi thêm các phần tử nguồn. Nó không cần lấy phần tử đầu tiên để đoán enum, nên nguồn rỗng không gây vấn đề suy ra kiểu.

Đây không phải cách tự bỏ qua dữ liệu không hợp lệ: nguồn và đối tượng `Class` vẫn phải phù hợp, không được `null`, và các phần tử phải đáp ứng hợp đồng `EnumSet`. Các ví dụ đặt trong lớp và cần import `EnumSet`, `Collection`.

## 4. clone cũng tạo tập độc lập

```java
EnumSet<Capability> cloned = selected.clone();
```

`EnumSet.clone()` công bố kiểu trả về phù hợp là `EnumSet<E>`, nên không cần ép kiểu từ `Object`. Tập kết quả chứa cùng các phần tử và có thể được sửa độc lập với tập nguồn.

Trong trường hợp đang có một `EnumSet`, `clone()` và `EnumSet.copyOf(selected)` đều thể hiện rõ việc sao chép. Chọn cách nhất quán với API và quy ước mã của ứng dụng; không cần tự duyệt từng hằng để thực hiện cùng việc.

Cũng như `copyOf`, đây là sao chép tập thành viên, không phải sao chép sâu các đối tượng hằng enum. Xem [EnumSet.clone](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/EnumSet.html#clone()).

## 5. complementOf lấy phần bù theo toàn bộ kiểu enum

Đặt `U` là tập tất cả hằng trong enum `Capability`, và `A` là tập đã chọn. Khi đó phần bù là:

```text
U = {READ, WRITE, EXPORT, AUDIT}
A = {READ, WRITE}
U \ A = {EXPORT, AUDIT}
```

Trong Java:

```java
EnumSet<Capability> remaining = EnumSet.complementOf(selected);
```

Kết quả có cùng kiểu phần tử với nguồn, nhưng chứa các hằng của kiểu đó chưa có trong nguồn. API tự xử lý miền enum; không cần dùng `ordinal()` rồi tự đảo một số bit theo một kích thước giả định.

Các trường hợp biên:

| Tập nguồn | Kết quả complementOf |
| --- | --- |
| Rỗng nhưng biết kiểu enum | Tất cả hằng của kiểu đó |
| Đã chứa mọi hằng | Tập rỗng cùng kiểu enum |
| Chứa một phần hằng | Những hằng còn lại |

Nếu một enum không khai báo hằng nào thì vũ trụ của nó rỗng; phần bù trong vũ trụ ấy cũng rỗng.

`complementOf` nhận một `EnumSet`, không nhận tùy ý một `List` hoặc `Set` tổng quát. Với nguồn tổng quát, trước tiên cần tạo `EnumSet` đúng kiểu và xử lý trường hợp rỗng như đã nêu ở mục 3.

Đối chiếu [EnumSet.complementOf](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/EnumSet.html#complementOf(java.util.EnumSet)).

### Tập bù không phải một view cập nhật trực tiếp

Sau khi tạo tập bù, sửa tập nguồn không tự sửa tập bù đã có. Nếu cần phản ánh lựa chọn mới, tính lại phần bù hoặc cập nhật theo quy tắc thuật toán rõ ràng.

Tương tự, sửa tập bù không xóa hoặc thêm vào nguồn. Đây là hai tập độc lập sau khi được tạo, không phải hai nửa của một cấu trúc tự đồng bộ.

## 6. Chương trình chạy đầy đủ

Lưu thành `EnumSetCopyComplementDemo.java`:

```java
import java.util.Collection;
import java.util.EnumSet;
import java.util.List;

public class EnumSetCopyComplementDemo {
    enum Capability {
        READ, WRITE, EXPORT, AUDIT
    }

    static <E extends Enum<E>> EnumSet<E> copyWithType(
            Class<E> elementType, Collection<? extends E> source) {
        EnumSet<E> result = EnumSet.noneOf(elementType);
        result.addAll(source);
        return result;
    }

    public static void main(String[] args) {
        EnumSet<Capability> selected = EnumSet.of(Capability.READ, Capability.WRITE);
        EnumSet<Capability> copied = EnumSet.copyOf(selected);
        EnumSet<Capability> cloned = selected.clone();

        copied.remove(Capability.WRITE);
        cloned.add(Capability.EXPORT);
        System.out.println("selected=" + selected);
        System.out.println("copied=" + copied);
        System.out.println("cloned=" + cloned);

        EnumSet<Capability> complement = EnumSet.complementOf(selected);
        System.out.println("initial complement=" + complement);
        selected.add(Capability.EXPORT);
        System.out.println("selected after change=" + selected);
        System.out.println("old complement=" + complement);
        System.out.println("fresh complement=" + EnumSet.complementOf(selected));

        EnumSet<Capability> emptyEnumSet = EnumSet.noneOf(Capability.class);
        Collection<Capability> widenedEmpty = emptyEnumSet;
        System.out.println("copy empty enum set=" + EnumSet.copyOf(emptyEnumSet));
        System.out.println("copy widened enum set=" + EnumSet.copyOf(widenedEmpty));

        List<Capability> emptyList = List.of();
        try {
            EnumSet.copyOf(emptyList);
        } catch (IllegalArgumentException expected) {
            System.out.println("copy empty list=rejected");
        }
        System.out.println("typed empty copy="
                + copyWithType(Capability.class, emptyList));

        System.out.println("complement of empty="
                + EnumSet.complementOf(emptyEnumSet));
        System.out.println("complement of all="
                + EnumSet.complementOf(EnumSet.allOf(Capability.class)));

        EnumSet<Capability> businessUniverse =
                EnumSet.of(Capability.READ, Capability.WRITE);
        EnumSet<Capability> chosen = EnumSet.of(Capability.READ);
        EnumSet<Capability> remaining = businessUniverse.clone();
        remaining.removeAll(chosen);
        System.out.println("business remaining=" + remaining);

        boolean doubleComplement =
                EnumSet.complementOf(EnumSet.complementOf(selected)).equals(selected);
        System.out.println("double complement=" + doubleComplement);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror EnumSetCopyComplementDemo.java
java EnumSetCopyComplementDemo
```

Stdout:

```text
selected=[READ, WRITE]
copied=[READ]
cloned=[READ, WRITE, EXPORT]
initial complement=[EXPORT, AUDIT]
selected after change=[READ, WRITE, EXPORT]
old complement=[EXPORT, AUDIT]
fresh complement=[AUDIT]
copy empty enum set=[]
copy widened enum set=[]
copy empty list=rejected
typed empty copy=[]
complement of empty=[READ, WRITE, EXPORT, AUDIT]
complement of all=[]
business remaining=[WRITE]
double complement=true
```

`copied` và `cloned` được thay đổi theo hai hướng nhưng không làm đổi `selected` ở ba dòng đầu. Sau khi nguồn thêm `EXPORT`, tập bù cũ vẫn giữ `EXPORT`, còn tập bù mới chỉ còn `AUDIT`.

Thứ tự in của `EnumSet` theo thứ tự khai báo hằng enum, không phải thứ tự thêm hoặc thứ tự phần tử trong một collection nguồn. Đây là hợp đồng của `EnumSet`, không nên suy từ một ví dụ `HashSet` rồi áp dụng sang.

## 7. Phần bù nghiệp vụ có thể nhỏ hơn toàn bộ enum

Giả sử một thao tác chỉ hỗ trợ `READ` và `WRITE`. Nếu người dùng đã chọn `READ`, phần “còn lại trong thao tác” là `[WRITE]`, không phải `[WRITE, EXPORT, AUDIT]`.

Khi ấy cần lấy hiệu theo một vũ trụ nghiệp vụ được định nghĩa riêng:

```java
EnumSet<Capability> supported =
        EnumSet.of(Capability.READ, Capability.WRITE);
EnumSet<Capability> chosen = EnumSet.of(Capability.READ);
EnumSet<Capability> remaining = supported.clone();
remaining.removeAll(chosen);
```

Không dùng `EnumSet.complementOf(chosen)` nếu muốn loại các khả năng không thuộc `supported`. `complementOf` không biết bối cảnh nghiệp vụ; nó luôn dùng toàn bộ kiểu enum của nguồn.

Nếu tập lựa chọn có thể chứa hằng ngoài phạm vi được hỗ trợ, cần quyết định từ chối hay lọc rõ ràng. Phép hiệu không tự là một bước xác thực rằng đầu vào đã nằm trong phạm vi cho phép.

### Thêm hằng enum có thể làm phần bù lớn hơn

Khi enum ở phiên bản mới thêm một hằng, vũ trụ mà `complementOf` sử dụng cũng có hằng mới đó. Nếu hằng chưa nằm trong nguồn, nó sẽ nằm trong phần bù được tính ở phiên bản mới.

Từ quy tắc ấy suy ra: nếu ứng dụng đang coi phần bù của một danh sách loại trừ là tập quyền/khả năng cho phép, thêm enum có thể tự mở rộng kết quả mà không cần sửa danh sách loại trừ. Cần kiểm thử hành vi phiên bản và xác định rõ chính sách mặc định thay vì coi phần bù luôn là một tập cố định.

## 8. Lỗi thường gặp và giới hạn

### Gọi copyOf với collection rỗng không biết kiểu

Đừng bắt mọi `IllegalArgumentException` rồi trả một tập rỗng của enum được đoán. Nếu biết kiểu ở API, truyền `Class<E>` hoặc dùng một `EnumSet` nguồn giữ đúng kiểu. Nếu chưa biết kiểu, phải sửa hợp đồng đầu vào thay vì tự đoán.

### Tưởng bản sao hoặc phần bù là không cho sửa

Kết quả vẫn là `EnumSet` có thể sửa. Nếu cần một hợp đồng không cho sửa, phải bọc hoặc công bố một kiểu/view phù hợp riêng. Cần phân biệt view chỉ đọc với bản sao: một view không cho sửa vẫn có thể phản ánh thay đổi từ tập gốc.

### Truyền null hoặc phần tử không hợp lệ

`EnumSet` không nhận phần tử `null`; `copyOf`/`complementOf` cũng không nhận nguồn `null`. Trong mã generic bình thường, kiểu giúp giữ cùng một enum; vẫn không nên dùng ép kiểu không an toàn để trộn những kiểu enum khác nhau.

### Coi sao chép là một giao dịch an toàn giữa nhiều luồng

`EnumSet` không tự đồng bộ hóa. Nếu nguồn đang được sửa bởi luồng khác, cần một giao thức truy cập phù hợp để có ý nghĩa ảnh chụp theo yêu cầu; việc gọi một phương thức sao chép không tự tạo khóa hay bảo đảm ảnh chụp nguyên tử.

### Tự thao tác biểu diễn bit

`EnumSet` quản lý biểu diễn nội bộ của nó theo kiểu enum. Đừng lấy phần bù bằng cách tự dùng `~` trên một số được ghép từ ordinal rồi cho rằng số đó luôn biểu diễn đúng mọi hằng; vừa dễ lẫn miền enum, vừa phụ thuộc những giả định không cần thiết.

## 9. Các tính chất có thể dùng để kiểm tra

Với một tập `A` của kiểu enum đã biết và `U = EnumSet.allOf(E.class)`, phần bù `C` theo toàn bộ kiểu thỏa mãn:

- `A` và `C` không có phần tử chung.
- Hợp của `A` và `C` bằng `U`.
- Lấy phần bù hai lần cho tập có cùng thành viên với `A`.
- Tạo bản sao rồi thêm/xóa ở bản sao không đổi thành viên của `A`.

Các tính chất này nói về tập thành viên ở thời điểm tính, không nói rằng các tập tiếp tục đồng bộ sau những lần sửa khác. Khi kiểm tra, dùng `equals` để so tập thành viên; không yêu cầu hai tập là cùng một đối tượng.

## 10. Tự kiểm tra

1. Gán `EnumSet<E> b = a` có tạo bản sao không?
2. Vì sao sao chép một EnumSet rỗng được nhưng sao chép List rỗng bằng copyOf có thể lỗi?
3. Nếu nguồn được khai báo là Collection nhưng đối tượng thật là EnumSet rỗng, copyOf có sao chép được không?
4. complementOf dùng tập hỗ trợ nghiệp vụ hay toàn bộ hằng của kiểu enum?
5. Sau khi tập nguồn đổi, phần bù đã tạo có tự đổi theo không?

Đáp án:

1. Không. Hai biến cùng tham chiếu tới một tập.
2. EnumSet vẫn biết kiểu enum của nó; collection rỗng không phải EnumSet không có phần tử để API xác định kiểu đó.
3. Có. Hợp đồng copyOf(Collection) xử lý riêng trường hợp đối tượng nguồn là EnumSet.
4. Toàn bộ hằng của kiểu enum. Với phạm vi nghiệp vụ riêng, dùng bản sao vũ trụ phù hợp rồi removeAll.
5. Không. Cần tính lại nếu muốn kết quả phản ánh trạng thái nguồn mới.

Khi sao chép hoặc lấy phần bù, hãy xác định rõ ba điều: kiểu enum lấy từ đâu, kết quả có độc lập với nguồn không và vũ trụ phần bù là toàn bộ enum hay một phạm vi nghiệp vụ riêng.
