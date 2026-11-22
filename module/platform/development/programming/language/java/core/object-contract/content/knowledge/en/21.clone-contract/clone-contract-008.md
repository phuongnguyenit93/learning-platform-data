# Phân biệt quy ước sao chép với các bảo đảm tuyệt đối của API

## 1. Vấn đề: lời hứa nào thật sự tồn tại khi gọi clone()?

Trong Java, phương thức `clone()` thường được giới thiệu là cách tạo “một bản sao giống đối tượng ban đầu”. Cách nói này tiện để bắt đầu, nhưng rất dễ dẫn đến ba suy luận quá mạnh:

- `x.clone() != x` luôn đúng.
- `x.clone().getClass() == x.getClass()` luôn đúng.
- `x.clone().equals(x)` luôn đúng.

Đây là những **kỳ vọng hoặc quy ước thiết kế** được nhắc tới trong tài liệu của `Object.clone()`, chứ **không phải ba mệnh đề tuyệt đối áp dụng cho mọi phương thức `clone()` mà một lớp tự ghi đè**. Tài liệu Java mô tả “general intent” (ý định chung) cho hai kỳ vọng đầu và nhận xét rằng điều thứ ba “typically” (thường) đúng; những điều này không được yêu cầu tuyệt đối.

Để hiểu chính xác, phải tách ba tầng:

1. **Hợp đồng ngôn ngữ/API của `Object.clone()`**: cách phương thức gốc hoạt động khi được gọi hợp lệ.
2. **Quy ước để lớp con triển khai `clone()` tử tế**: phương thức public/covariant, gọi `super.clone()` khi phù hợp, trả về một bản sao có ý nghĩa và bảo vệ các invariant.
3. **Chính sách sao chép của từng lớp**: sao chép nông hay sâu, trường nào được chia sẻ, exception nào được công bố và liệu lớp có cung cấp cách sao chép khác hay không.

Không nên nhìn vào tên `clone()` rồi tự kết luận đối tượng trả về hoàn toàn độc lập, mọi trường đều tương đương, constructor được gọi lại, hay tất cả lớp Java đều hỗ trợ thao tác đó.

## 2. Phần được API Object.clone() định nghĩa

Chữ ký của phương thức gốc trong `java.lang.Object`:

```java
protected native Object clone() throws CloneNotSupportedException;
```

Đây là **khai báo API minh họa**, không phải đoạn mã để tự biên dịch riêng. Có ba chi tiết ngay từ chữ ký:

- `protected`: một lời gọi `someObject.clone()` thường **không truy cập được từ code bên ngoài** nếu lớp không công khai phương thức này. `Cloneable` tự nó không tạo ra `public clone()`.
- `Object` là kiểu trả về khai báo ban đầu; lớp con có thể ghi đè và trả về kiểu cụ thể hơn (*covariant return type*), chẳng hạn `public Employee clone()`.
- `CloneNotSupportedException` là checked exception mà `Object.clone()` công bố. Một override có thể xử lý bên trong và không khai báo exception đó.

Với triển khai **`Object.clone()` mặc định**, theo tài liệu:

1. Khi class runtime không triển khai `Cloneable`, việc gọi cơ chế `Object.clone()` thông thường sẽ ném `CloneNotSupportedException`. **Mảng là trường hợp đặc biệt**: các array được xem là hỗ trợ clone.
2. Khi clone thành công, cơ chế gốc tạo đối tượng mới có **cùng lớp runtime** với đối tượng ban đầu.
3. Các trường của đối tượng mới được khởi tạo từ giá trị các trường tương ứng của đối tượng nguồn, **như phép gán từng trường**.
4. Nội dung của các object được tham chiếu bởi những trường đó **không tự được clone tiếp**: đây là *shallow copy* (sao chép nông).
5. Việc tạo object bằng `Object.clone()` không đi theo đường gọi constructor thông thường của class như `new`.

Các điểm trên mô tả **hành vi của cơ chế gốc** khi được gọi và trả về thành công. Một lớp có thể cung cấp **override `clone()` của riêng nó**, trong đó Java không tự chèn lời gọi `super.clone()`, không tự kiểm tra từng kỳ vọng thiết kế và không tự bổ sung deep copy.

### Cần hiểu đúng Cloneable

`java.lang.Cloneable` là **marker interface**, tức không khai báo bất kỳ phương thức nào. Nó là tín hiệu mà `Object.clone()` kiểm tra để quyết định có được thực hiện sao chép gốc hay không.

```java
final class MarkerOnly implements Cloneable {
    private final int id = 1;
}
```

*Đây là định nghĩa lớp minh họa.* Lớp `MarkerOnly` có `Cloneable` nhưng mã sử dụng bên ngoài **không tự nhiên gọi được** `new MarkerOnly().clone()`, vì phương thức `clone()` kế thừa từ `Object` vẫn là `protected`. Muốn expose API clone, lớp phải chủ động khai báo override `public` hoặc một phương thức sao chép khác.

Ngược lại, một override `clone()` tự tạo object bằng constructor mà **không dùng `super.clone()`** có thể chạy mà không cần marker `Cloneable`. Vì thế không nên nói `implements Cloneable` là điều kiện bắt buộc để *mọi phương thức có tên clone* đều chạy; nó là điều kiện được cơ chế `Object.clone()` mặc định kiểm tra (ngoại trừ array).

## 3. Ba kỳ vọng thường gặp: quy ước hay bảo đảm?

| Mệnh đề | Với Object.clone() gốc thành công | Với override clone() tùy ý | Cách diễn đạt đúng |
| --- | --- | --- | --- |
| `copy != original` | Đối tượng mới được tạo, nên đúng | Override có thể trả `this` | Ý định thông thường của clone, **không phải bảo đảm tuyệt đối** của mọi override. |
| `copy.getClass() == original.getClass()` | Đúng do đối tượng mới cùng lớp runtime | Override có thể trả một object thuộc lớp khác nếu kiểu trả về cho phép | Kỳ vọng tự nhiên, nhưng **không được cưỡng chế** cho mọi override. |
| `copy.equals(original)` | Không nhất thiết: `Object.equals()` mặc định dùng identity | Tùy quy tắc `equals()` và quyết định clone | Thường mong đợi với value object, **không phải điều kiện bắt buộc**. |
| Các trường của copy độc lập hoàn toàn | Không: chỉ shallow copy | Tùy override sao chép nông/sâu | Phải đọc chính sách sao chép của lớp. |
| Gọi constructor của class | Không theo đường gọi constructor thường của `Object.clone()` | Override dùng `new` có thể gọi constructor | Không tổng quát hóa giữa các chiến lược. |
| Luôn hỗ trợ gọi từ bên ngoài | Không: phương thức gốc `protected` | Có thể override `public` | Kiểm tra chữ ký API của lớp đang dùng. |

### Kỳ vọng 1: hai đối tượng có khác nhau không?

Với code dùng `super.clone()` đúng cách, thông thường có object mới nên `copy != source`. Tuy nhiên, một lớp có thể định nghĩa:

```java
@Override
public SomeType clone() {
    return this; // Vi phạm ý định bản sao độc lập, nhưng là code override hợp lệ.
}
```

*Đoạn này chỉ minh họa một override nằm bên trong lớp `SomeType`.* JVM không cưỡng chế lời gọi `super.clone()` trong phương thức override. Đây thường là **thiết kế clone tồi** vì người gọi có thể kỳ vọng một đối tượng riêng; nhưng nó minh họa lý do không được xem quy ước “khác tham chiếu” là bảo đảm tuyệt đối của bất kỳ API mang tên `clone()` nào.

### Kỳ vọng 2: có giữ đúng lớp runtime không?

`Object.clone()` gốc tạo bản sao đúng lớp runtime. Nhưng một override công bố kiểu trả về `Object` có thể trả một object bất kỳ:

```java
@Override
public Object clone() {
    return new Object(); // Không giữ lớp runtime của this.
}
```

*Đây là đoạn override minh họa bên trong một class; không phải thiết kế nên dùng trong ứng dụng.* Java kiểm tra kiểu trả về theo chữ ký phương thức và quy tắc override, chứ không tự yêu cầu `result.getClass() == this.getClass()` cho tất cả override.

Một override có kiểu trả về cụ thể hơn, ví dụ `public Employee clone()`, đã giới hạn được các kiểu có thể trả về ở mức biên dịch, nhưng nếu `Employee` cho phép kế thừa thì object trả về vẫn có thể là một subtype khác. Vì vậy cũng phải hiểu rõ semantics của lớp, không lấy việc phương thức tên `clone` làm bằng chứng.

### Kỳ vọng 3: clone có bằng bản gốc theo equals() không?

Ngay cả khi dùng `super.clone()` và nhận một object khác tham chiếu có **các trường giống hệt**, `clone.equals(original)` vẫn có thể là `false` nếu class không ghi đè `equals()`, bởi `Object.equals()` mặc định so identity.

Với value object triển khai `equals()` dựa trên các trường giá trị, việc sao chép giữ nguyên giá trị thường dẫn tới `equals() == true`. Nhưng đó là kết quả của **định nghĩa equality của lớp**, không phải tính chất mà tên `clone()` tự áp đặt.

Cần kiểm tra cả chiều ngược: `copy.equals(original)` và `original.equals(copy)` phải tuân theo hợp đồng đối xứng của `equals()`, nếu lớp định nghĩa equality. Một clone không cứu được thiết kế `equals()` vốn thiếu nhất quán.

## 4. Shallow copy: sao chép trường chứ không tự sao chép cả đồ thị object

Một `Object.clone()` thành công hoạt động tương tự việc sao chép giá trị từng field:

- Với `int`, `boolean`, `double`...: giá trị nguyên thủy được sao chép.
- Với field tham chiếu như `String`, `Address`, `List`: **tham chiếu** được sao chép. Hai object có thể cùng trỏ tới một object con.
- Nếu field được khai báo `final` và giữ một `List` hoặc object mutable, `final` chỉ ngăn gán lại field, **không** tự làm object mà nó trỏ tới bất biến.

Sơ đồ:

```text
Trước clone:
source -------> Employee A ------address------> Address X

Sau super.clone():
source -------> Employee A ------address------┐
                                             ├--> Address X
shallow ------> Employee B ------address------┘

Sau copy method sao chép thêm Address:
source -------> Employee A ------address------> Address X
isolated -----> Employee C ------address------> Address Y
```

Khi `Address X.city` bị thay đổi qua `shallow.address`, `source.address.city` cũng đổi vì chúng đang dùng chung một `Address`. `isolated` có `Address Y` riêng thì không bị ảnh hưởng bởi thay đổi đó.

Một **deep copy** thực sự cần định nghĩa các object con nào phải sao chép, có chia sẻ một số tham chiếu bất biến không, xử lý quan hệ vòng thế nào và xử lý tài nguyên như file/socket/lock ra sao. Java không có một `Object.deepClone()` tiêu chuẩn tự giải quyết tất cả những vấn đề này.

## 5. Ví dụ Java 17+ chạy được: minh họa cả cơ chế gốc và override bất thường

Tạo tệp `CloneGuaranteeDemo.java`:

```java
public class CloneGuaranteeDemo {

    static final class Address {
        String city;

        Address(String city) {
            this.city = city;
        }
    }

    static final class Employee implements Cloneable {
        private final String name;
        private final Address address;

        Employee(String name, Address address) {
            this.name = name;
            this.address = address;
        }

        @Override
        public Employee clone() {
            try {
                return (Employee) super.clone();
            } catch (CloneNotSupportedException ex) {
                // Employee implements Cloneable, nên không mong đợi exception.
                throw new AssertionError(ex);
            }
        }

        Employee copyWithIndependentAddress() {
            return new Employee(name, new Address(address.city));
        }
    }

    static final class NotCloneable {
        @Override
        public NotCloneable clone() throws CloneNotSupportedException {
            return (NotCloneable) super.clone();
        }
    }

    static final class ReturnsSelf implements Cloneable {
        @Override
        public ReturnsSelf clone() {
            return this; // Cố ý làm sai quy ước clone; chỉ để minh họa.
        }
    }

    static final class ReturnsOtherType implements Cloneable {
        @Override
        public Object clone() {
            return new Object(); // Cố ý làm sai kỳ vọng cùng lớp runtime.
        }
    }

    public static void main(String[] args) {
        Employee original = new Employee("An", new Address("Hà Nội"));
        Employee shallow = original.clone();
        Employee isolated = original.copyWithIndependentAddress();

        System.out.println(original != shallow);
        System.out.println(original.getClass() == shallow.getClass());
        System.out.println(original.equals(shallow));
        System.out.println(original.address == shallow.address);
        System.out.println(original.address == isolated.address);

        shallow.address.city = "Huế";
        System.out.println(original.address.city);
        System.out.println(isolated.address.city);

        try {
            new NotCloneable().clone();
        } catch (CloneNotSupportedException ex) {
            System.out.println("CloneNotSupportedException");
        }

        ReturnsSelf self = new ReturnsSelf();
        System.out.println(self.clone() == self);

        ReturnsOtherType odd = new ReturnsOtherType();
        System.out.println(odd.clone().getClass() == odd.getClass());

        int[][] matrix = {{1, 2}};
        int[][] arrayCopy = matrix.clone();
        System.out.println(matrix != arrayCopy);
        System.out.println(matrix[0] == arrayCopy[0]);
    }
}
```

Biên dịch và chạy từ thư mục chứa file bằng JDK 17 trở lên:

```bash
javac CloneGuaranteeDemo.java
java CloneGuaranteeDemo
```

Stdout chính xác:

```text
true
true
false
true
false
Huế
Hà Nội
CloneNotSupportedException
true
false
true
true
```

Giải thích:

1. `Employee` triển khai `Cloneable`, expose `public clone()` và gọi `super.clone()`. Bản `shallow` khác tham chiếu nhưng giữ cùng lớp runtime.
2. `Employee` không ghi đè `equals()`. Dù bản sao nông giữ nguyên giá trị trường ban đầu, `original.equals(shallow)` vẫn là `false` theo identity equality mặc định.
3. `original.address == shallow.address` là `true`; chỉ tham chiếu `address` được copy. Ngược lại `copyWithIndependentAddress()` tạo `Address` mới, nên phép so tham chiếu trả `false`.
4. Sau khi sửa `shallow.address.city` thành `Huế`, bản gốc cũng thấy `Huế` vì chia sẻ object con; bản `isolated` vẫn `Hà Nội`.
5. `NotCloneable` cố gọi `super.clone()` nhưng không triển khai `Cloneable`: phương thức gốc ném `CloneNotSupportedException`. Lớp vẫn có thể khai báo override `public`; marker ảnh hưởng **cơ chế gốc**, không quyết định tên/chữ ký method có tồn tại hay không.
6. `ReturnsSelf` có override trả `this`; phép kiểm tra `self.clone() == self` in `true`. Đây là phương thức hợp lệ về cú pháp, nhưng **không thực hiện ý định tạo bản sao mới**.
7. `ReturnsOtherType` ghi đè `clone()` trả `new Object()`; phép kiểm tra cùng lớp runtime in `false`. Như vậy “clone luôn giữ đúng lớp” cũng không được áp đặt lên override tùy ý.
8. Một mảng hai chiều `int[][]` vẫn có clone công khai theo cơ chế array. `matrix != arrayCopy` là `true`, nhưng `matrix[0] == arrayCopy[0]` cũng `true`: mảng ngoài mới, các mảng con vẫn được chia sẻ.

Hai lớp `ReturnsSelf` và `ReturnsOtherType` chỉ phục vụ chứng minh ranh giới API. **Không nên triển khai clone theo hai kiểu này trong code ứng dụng thông thường**: chúng phá kỳ vọng mà caller dễ dựa vào.

## 6. Điều gì là quy ước triển khai clone() tốt?

Một lớp chủ động hỗ trợ clone nên có chính sách có thể hiểu và kiểm chứng. Các lựa chọn thường gặp:

1. **Public API rõ ràng:** nếu người dùng bên ngoài cần gọi clone, cung cấp `public clone()` với kiểu trả về cụ thể, thay vì mặc nhiên trông chờ vào `protected Object.clone()`.
2. **Gọi super.clone khi dùng cơ chế chuẩn:** override của lớp có `Cloneable` thường bắt đầu bằng `super.clone()` để lấy bản sao nông của đúng lớp runtime. Điều này đặc biệt quan trọng khi có kế thừa; không thể luôn thay an toàn bằng `new Base(...)` vì object thực có thể là subclass.
3. **Sao chép thành phần mutable theo chính sách:** chỉ chia sẻ object bất biến (như `String`) hoặc những tài nguyên được thiết kế cho việc chia sẻ; copy thêm khi yêu cầu độc lập.
4. **Giữ invariant:** xác định xem các trường `final` mutable, cache, lock, handle file, thread và tài nguyên runtime có thể được sao chép hay không. Một bản chép từng field không tự có ngữ nghĩa an toàn.
5. **Kiểm tra hậu điều kiện:** với lớp có hợp đồng clone, có thể kiểm tra `copy != source`, lớp runtime tương thích, dữ liệu cần giữ nguyên, các object con cần độc lập và các trường được phép chia sẻ.
6. **Ghi rõ mức sao chép:** “shallow”, “deep cho Address”, “giữ chung cache” hoặc “không hỗ trợ clone” giúp caller không phải tự đoán.

Một mẫu triển khai ở lớp `final` đơn giản:

```java
final class Point implements Cloneable {
    private final int x;
    private final int y;

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }

    @Override
    public Point clone() {
        try {
            return (Point) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }
}
```

*Đây là định nghĩa lớp minh họa, không phải chương trình có `main`.* `Point` chỉ chứa hai trường nguyên thủy, nên shallow copy đã đủ độc lập về các giá trị đó. Tuy vậy, lớp **chưa ghi đè `equals()`**, nên dù cả hai có cùng `x/y` thì `clone.equals(original)` vẫn `false`. Nếu domain muốn value equality, nên định nghĩa thêm `equals()/hashCode()` tương thích hoặc cân nhắc sử dụng một `record Point(int x, int y)` bất biến.

### Có cần mọi lớp implements Cloneable không?

Không. Có những lớp không nên cho phép sao chép: kết nối đang mở, đối tượng quản lý khóa, các thành phần chứa resource sở hữu duy nhất, các đối tượng điều phối vòng đời đặc biệt. Có lớp muốn sao chép nhưng không muốn dùng `Cloneable` vì API lịch sử này có giới hạn về quyền truy cập, checked exception, invariant và sao chép nông. Copy constructor hoặc factory thường mô tả chính sách rõ hơn:

```java
Employee duplicate = original.copyWithIndependentAddress();
```

Trong trường hợp ví dụ ở mục 5, method này chủ động tạo `Address` mới, cho caller biết rõ phạm vi độc lập của bản sao. Nhưng đây **không phải deep clone tổng quát**: nếu `Employee` có thêm một đồ thị object mutable khác, cần định nghĩa riêng việc xử lý nó.

## 7. Array.clone() là ngoại lệ API cần biết

Các kiểu mảng Java là đối tượng. Mảng được xem là triển khai `Cloneable` và hỗ trợ phương thức `clone()` công khai; một biểu thức như:

```java
int[] values = {1, 2, 3};
int[] copy = values.clone();

System.out.println(values == copy); // false
System.out.println(java.util.Arrays.equals(values, copy)); // true
```

*Đoạn trên là các câu lệnh minh họa trong một phương thức.* Phần tử nguyên thủy được sao chép theo giá trị, nên sửa `copy[0]` không thay `values[0]`.

Với mảng chứa tham chiếu như `StringBuilder[]` hoặc `Address[]`, chỉ **mảng ngoài** là object mới; phần tử trong mảng vẫn trỏ đến các object cũ:

```java
StringBuilder[] a = {new StringBuilder("A")};
StringBuilder[] b = a.clone();

System.out.println(a != b);       // true
System.out.println(a[0] == b[0]); // true
```

Mảng hai chiều cũng là mảng các mảng; `matrix.clone()` không tự sao chép từng hàng. Nếu cần bản sao không chia sẻ mảng con, phải clone từng hàng hoặc chuyển đổi bằng cấu trúc dữ liệu phù hợp. **Không được chuyển từ “array có clone” sang kết luận “array clone luôn sâu”.**

## 8. Copy constructor, factory method và immutable object

Trong code mới, đôi khi không cần `clone()`:

| Nhu cầu | Cách tiếp cận | Lưu ý |
| --- | --- | --- |
| Sao chép một value object nhỏ | Copy constructor hoặc `static copyOf(...)` | Chính sách sao chép nằm rõ trong constructor/factory. |
| Đối tượng bất biến | Thường có thể giữ nguyên đối tượng; tạo bản mới khi muốn thay giá trị | Tránh sao chép không cần thiết; tùy hợp đồng API. |
| Đối tượng có field tham chiếu mutable | Copy method chủ động copy trường cần tách | Phải bảo vệ bất biến và tránh chia sẻ không mong muốn. |
| Lớp hiện có với `public clone()` được tài liệu hóa | Gọi theo chính sách của lớp | Kiểm tra shallow/deep và exception cụ thể. |
| Đồ thị phức tạp, tài nguyên hoặc quan hệ vòng | Sao chép chuyên biệt theo nghiệp vụ | Clone mặc định không thể suy ra ownership hay vòng đời. |

Copy constructor có ưu điểm là biểu đạt **rõ constructor nào được gọi, trường nào được tái tạo**. Nhưng với hierarchy mở, constructor của superclass không tự động tạo bản sao đúng subtype nếu không có cơ chế riêng; ngược lại `super.clone()` tạo đối tượng cùng runtime class nhưng có rủi ro copy state quá máy móc. Không có một giải pháp áp dụng tốt cho mọi loại đối tượng.

Một lớp bất biến có thể lựa chọn trả lại `this` từ phương thức có tên `copy()` nếu hợp đồng phương thức nói rõ như vậy. Tuy nhiên, nếu API hứa “tạo object khác tham chiếu” thì trả `this` không đạt yêu cầu. Vì vậy **ngôn ngữ mô tả hợp đồng của phương thức quan trọng hơn chính tên của nó**.

## 9. Các sai lầm phổ biến khi suy diễn bảo đảm từ clone()

### Sai lầm 1: implements Cloneable nghĩa là có public clone()

`Cloneable` không khai báo method. Lớp vẫn phải expose một `public clone()` nếu code bên ngoài cần gọi; `Object.clone()` gốc là `protected`.

### Sai lầm 2: clone luôn trả object mới và khác tham chiếu

`super.clone()` thành công tạo object mới, nhưng override có thể trả `this`. Tài liệu `Object.clone()` gọi đây là ý định thông thường, **không phải yêu cầu tuyệt đối lên mọi override**.

### Sai lầm 3: clone luôn có cùng lớp và bằng nhau theo equals()

Cùng lớp runtime là tính chất của `Object.clone()` gốc khi thành công; override có thể trả kiểu khác. `equals()` thường là identity equality nếu lớp không ghi đè, nên copy khác tham chiếu sẽ `false` dù các field có cùng giá trị.

### Sai lầm 4: clone tự gọi constructor và chạy lại validation

`Object.clone()` sao chép state ở mức field, không đi qua constructor thông thường. Nếu invariant phụ thuộc việc khởi tạo mới, bản sao có thể không phù hợp. Override tự tạo bằng `new` lại có semantics khác, vì vậy không thể khẳng định chung mọi `clone()` đều bỏ qua constructor.

### Sai lầm 5: clone luôn là deep copy

Không. `Object.clone()` chỉ sao chép nông. `final List<Address>` hoặc `final Address` vẫn có thể chia sẻ nội dung mutable. Muốn độc lập phải sao chép các tầng liên quan theo chính sách của lớp.

### Sai lầm 6: clone nhất định sẽ ném CloneNotSupportedException nếu không implements Cloneable

Đúng khi gọi cơ chế `Object.clone()` gốc trên đối tượng không hỗ trợ, trừ trường hợp đặc biệt array. Nhưng một override tự tạo object bằng constructor có thể hoạt động mà không dùng marker. Phải phân biệt cơ chế gốc với phương thức do lớp tự cung cấp.

### Sai lầm 7: không cần test vì clone chỉ chép object

Một object phức tạp có thể chứa cấu trúc mutable, cache, reference vòng, lock hay resource không thể chia sẻ vô điều kiện. Hãy kiểm thử đúng chính sách sao chép, chẳng hạn sửa một bản có ảnh hưởng bản kia ở các field không được phép chia sẻ hay không.

## 10. Kiểm chứng hậu điều kiện theo chính sách cụ thể

Với một lớp có `clone()`, hãy xác định rõ “bản sao đúng” gồm những điều kiện nào và đánh giá từng điều kiện riêng:

| Điều kiện cần hỏi | Kiểm tra thích hợp |
| --- | --- |
| Có cần object khác tham chiếu? | `copy != original`. |
| Có cần cùng lớp runtime? | `copy.getClass() == original.getClass()`. |
| Có cần bình đẳng logic tại lúc sao chép? | `copy.equals(original)` và kiểm tra hợp đồng `equals/hashCode`. |
| Field nguyên thủy có giữ nguyên? | Đối chiếu từng giá trị được định nghĩa trong contract. |
| Field tham chiếu nào được phép chia sẻ? | Kiểm tra `copy.ref == original.ref` khi cần. |
| Field tham chiếu nào buộc phải độc lập? | Kiểm tra khác tham chiếu và thử thay đổi bản sao. |
| Constructor/invariant có được bảo đảm? | Kiểm tra cách dựng object thực tế của phương thức được dùng. |
| Có thể trả về exception hoặc giá trị không hợp lệ? | Đọc chữ ký và tài liệu lớp; kiểm thử các điều kiện từ chối. |

Một lời kiểm tra `copy != original` đơn lẻ không chứng minh nội dung được sao chép đúng. Tương tự, `copy.equals(original)` là `true` cũng không chứng minh hai bản có object con độc lập: chúng có thể cùng giữ một `List` mutable và cùng thay đổi về sau. Mỗi tiêu chí là một phần của **hợp đồng sao chép của lớp**, không phải một hệ quả tự động từ tên `clone()`.

Nếu lớp sử dụng kế thừa, nên kiểm thử với instance subclass thực sự. Override của superclass gọi `super.clone()` có thể tạo đúng runtime class nhưng các field mới của subclass được chép nông mà subclass chưa dự tính; trong một số thiết kế cần override bổ sung để sao chép các thành phần đó đúng cách.

## 11. Tự kiểm tra

**Câu 1.** `Cloneable` có định nghĩa một phương thức `clone()` công khai không?  
**Đáp án:** Không. Đây là marker interface; phương thức `Object.clone()` kế thừa vẫn là `protected` trừ khi lớp expose nó.

**Câu 2.** `x.clone() != x` có đúng với mọi override `clone()` không?  
**Đáp án:** Không. Đây là ý định thông thường, nhưng override có thể trả chính `this`. Với `Object.clone()` gốc thành công, object mới được tạo.

**Câu 3.** `clone.getClass() == original.getClass()` có phải bảo đảm tuyệt đối của mọi phương thức mang tên `clone` không?  
**Đáp án:** Không. `Object.clone()` gốc tạo bản sao cùng runtime class, nhưng override tự viết có thể trả kiểu khác nếu chữ ký cho phép.

**Câu 4.** `Employee` không ghi đè `equals()`; nếu `super.clone()` trả object khác tham chiếu nhưng cùng trường, `clone.equals(original)` là gì?  
**Đáp án:** `false` vì `Object.equals()` mặc định so identity.

**Câu 5.** Field `private final Address address` có khiến `super.clone()` tạo `Address` mới không?  
**Đáp án:** Không. `final` không làm nội dung mutable của `Address` thành bất biến; shallow clone chia sẻ cùng tham chiếu.

**Câu 6.** Một class không implements `Cloneable` nhưng ghi `public X clone() { return new X(...); }` có thể chạy không?  
**Đáp án:** Có, khi phương thức tự dựng object và không gọi `Object.clone()` gốc. Đây là chính sách clone tùy biến; nên tài liệu hóa rõ.

**Câu 7.** Clone mảng hai chiều có tự clone từng hàng không?  
**Đáp án:** Không. `int[][]` là mảng chứa `int[]`; `clone()` tạo mảng ngoài mới, còn các mảng hàng vẫn chia sẻ.

**Câu 8.** Kiểm tra clone bằng `equals() == true` đã đủ đảm bảo deep copy chưa?  
**Đáp án:** Chưa. Equality có thể đúng ngay cả khi bản gốc và bản sao chia sẻ object mutable; phải kiểm tra chính sách độc lập của từng thành phần.

**Câu 9.** Vì sao copy constructor có thể dễ hiểu hơn `Object.clone()` với object có tài nguyên?  
**Đáp án:** Constructor/factory cho phép chỉ rõ object con hoặc tài nguyên nào cần tạo lại, chia sẻ hoặc từ chối sao chép, thay vì copy mọi field tự động.

**Câu 10.** Nếu một API chỉ nói “hỗ trợ clone”, điều gì cần xem trước khi dựa vào nó?  
**Đáp án:** Quyền truy cập và kiểu trả về, khả năng ném exception, liệu phương thức gọi cơ chế gốc hay tự dựng object, mức shallow/deep, chính sách chia sẻ mutable state và các hậu điều kiện lớp thực sự cam kết.

**Ghi nhớ:** `Object.clone()` gốc có hành vi xác định khi gọi thành công: tạo object mới cùng lớp runtime và sao chép nông các field. Nhưng những phát biểu kiểu “mọi clone khác tham chiếu”, “mọi clone cùng lớp”, “mọi clone equals bản gốc” là các **quy ước/kỳ vọng**, không phải bảo đảm cưỡng chế đối với mọi override. Một API sao chép đáng tin phải công bố chính sách thực tế, giữ invariant và được kiểm tra theo nhu cầu của lớp.