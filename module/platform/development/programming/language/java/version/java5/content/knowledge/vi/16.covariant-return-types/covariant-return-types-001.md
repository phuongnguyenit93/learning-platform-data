# Ghi đè phương thức với kiểu trả về tham chiếu cụ thể hơn

## Khái niệm: giữ hợp đồng chung, cung cấp kết quả cụ thể hơn

Trong Java, một phương thức ghi đè có thể dùng kiểu trả về tham chiếu là kiểu con của kiểu trả về mà phương thức cha đã khai báo. Cơ chế này được gọi là **kiểu trả về đồng biến (covariant return type)**.

Ví dụ:

- Phương thức cha khai báo trả `Animal`.
- Phương thức con khai báo trả `Dog`.
- `Dog` là kiểu con của `Animal`.

Một kết quả dùng được như `Dog` cũng dùng được như `Animal`, nên lớp con vẫn giữ cam kết kiểu của lớp cha, đồng thời cung cấp thông tin cụ thể hơn cho mã làm việc trực tiếp với lớp con.

Đây là cơ chế hiện hành của Java. Chương trình trong bài chạy trên JDK 17 trở lên và không cần thư viện ngoài.

## Vì sao cần kiểu trả về cụ thể hơn?

Giả sử lớp cha định nghĩa một phương thức tạo đối tượng chung:

```java
Animal create(String name)
```

Một lớp con chỉ chuyên tạo chó. Nếu phương thức con vẫn khai báo trả `Animal`, mã biết chắc mình đang dùng lớp chuyên tạo chó vẫn chỉ nhận được cam kết kiểu `Animal`.

Với kiểu trả về đồng biến, lớp con có thể khai báo:

```java
Dog create(String name)
```

Phần mã gọi qua lớp con nhận ngay một `Dog`, không phải tự ép kết quả từ `Animal` về `Dog`.

Lợi ích không chỉ là bớt một phép ép kiểu. Quan trọng hơn, ý nghĩa “cách tạo này trả đối tượng dùng được như Dog” trở thành một phần của chữ ký được trình biên dịch kiểm tra.

Các dòng khai báo trên chỉ minh họa chữ ký; chương trình đầy đủ phía dưới có toàn bộ cấu trúc lớp và phần thân phương thức.

## Quan hệ kiểu cần đi theo hướng nào?

Với phương thức không generic thông thường, nếu kiểu trả về của phương thức cha là `R`, kiểu trả về tham chiếu của phương thức ghi đè có thể giữ nguyên `R` hoặc thu hẹp thành kiểu con phù hợp của `R`.

| Kiểu trả về ở cha | Kiểu trả về ở con | Đánh giá |
| --- | --- | --- |
| `Animal` | `Dog`, với `Dog extends Animal` | Hợp lệ về quan hệ kiểu trả về |
| `Object` | `String` | Hợp lệ |
| `Number` | `Integer` | Hợp lệ |
| `Dog` | `Animal` | Không hợp lệ: mở rộng cam kết kết quả |
| `Number` | `String` | Không hợp lệ: không có quan hệ kiểu con cần thiết |
| `int` | `long` | Không hợp lệ: đây không phải đồng biến kiểu tham chiếu |

Từ “cụ thể hơn” nói về quan hệ kiểu, không nói về việc dữ liệu chứa nhiều thông tin hơn hay một lớp có tên dài hơn.

Kiểu con có thể liên quan tới interface: chẳng hạn kiểu kết quả ở cha là một interface, còn kiểu kết quả ở con là một lớp triển khai interface đó. Không bắt buộc hai kiểu kết quả chỉ có quan hệ kế thừa lớp trực tiếp.

Đặc tả dùng khái niệm khả năng thay thế kiểu trả về; xem [JLS §8.4.5](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.5).

## Cần có quan hệ ghi đè trước

Kiểu trả về đồng biến không tự biến một phương thức mới thành phương thức ghi đè.

Cần xem:

1. Quan hệ kiểu giữa lớp/interface khai báo phương thức.
2. Tên và chữ ký tham số theo quy tắc ghi đè.
3. Khả năng truy cập phương thức cha.
4. Các giới hạn như `final`, `static` hoặc `private`.
5. Kiểu trả về tương thích.

Với các phương thức không generic thông thường, cần cùng tên và cùng danh sách kiểu tham số. Không được vừa đổi tham số từ `String` sang `Object`, vừa đổi kiểu trả về, rồi cho rằng đây vẫn là ghi đè chỉ vì tên phương thức giống nhau.

Nên viết `@Override` để trình biên dịch kiểm tra ý định. Annotation này không tạo quy tắc đồng biến, nhưng giúp phát hiện khai báo không thực sự tương ứng. Xem [Override](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Override.html).

## Ví dụ chạy đầy đủ: factory trả Animal và Dog

Lưu thành `CovariantReturnDemo.java`:

```java
public class CovariantReturnDemo {
    static class Animal {
        private final String name;

        Animal(String name) {
            this.name = name;
        }

        String name() {
            return name;
        }

        String sound() {
            return "unknown";
        }
    }

    static class Dog extends Animal {
        Dog(String name) {
            super(name);
        }

        @Override
        String sound() {
            return "woof";
        }

        String fetch() {
            return name() + " fetched";
        }
    }

    interface AnimalMaker {
        Animal create(String name);
    }

    static class AnimalFactory implements AnimalMaker {
        @Override
        public Animal create(String name) {
            return new Animal(name);
        }
    }

    static class DogFactory extends AnimalFactory {
        @Override
        public Dog create(String name) {
            return new Dog(name);
        }
    }

    public static void main(String[] args) {
        DogFactory specific = new DogFactory();
        Dog dog = specific.create("Milo");
        System.out.println("specific=" + dog.fetch());

        AnimalFactory general = specific;
        Animal animal = general.create("Luna");
        System.out.println("runtime=" + animal.getClass().getSimpleName());
        System.out.println("sound=" + animal.sound());

        AnimalMaker contract = specific;
        Animal throughInterface = contract.create("Rex");
        System.out.println("interface.runtime="
                + throughInterface.getClass().getSimpleName());
        System.out.println("interface.sound=" + throughInterface.sound());
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 CovariantReturnDemo.java
java CovariantReturnDemo
```

Kết quả:

```text
specific=Milo fetched
runtime=Dog
sound=woof
interface.runtime=Dog
interface.sound=woof
```

## Phân tích mối quan hệ trong ví dụ

### Animal và Dog là các kiểu kết quả

`Dog extends Animal`, nên một tham chiếu `Dog` có thể dùng tại nơi cần `Animal`.

`AnimalFactory.create(String)` khai báo trả `Animal`. `DogFactory.create(String)` ghi đè và khai báo trả `Dog`. Tham số `String name` được giữ nguyên.

Phương thức con trả `new Dog(name)`, phù hợp với chữ ký cụ thể hơn. Trình biên dịch không cho phép phương thức khai báo trả `Dog` mà lại tùy ý trả một đối tượng chỉ là `Animal`.

### Lời gọi qua DogFactory có kết quả tĩnh là Dog

Ở đoạn:

```java
DogFactory specific = new DogFactory();
Dog dog = specific.create("Milo");
```

kiểu khai báo của biến nhận lời gọi là `DogFactory`. Mã nhìn thấy chữ ký `Dog create(String)`, nên nhận kết quả bằng biến `Dog` mà không cần ép kiểu.

Sau đó có thể gọi `dog.fetch()`, một phương thức chỉ có ở `Dog`.

### Lời gọi qua kiểu cha vẫn giữ góc nhìn Animal

Ở đoạn:

```java
AnimalFactory general = specific;
Animal animal = general.create("Luna");
```

đối tượng factory thực tế vẫn là `DogFactory`, nên phần thực thi được chọn là phương thức ghi đè trong `DogFactory`. Kết quả thực tế là một `Dog`.

Nhưng biểu thức `general.create("Luna")` được kiểm tra dựa trên kiểu khai báo `AnimalFactory`, có kiểu trả về `Animal`.

Vì vậy, dòng sau **không hợp lệ nếu chỉ thêm vào chương trình nguyên trạng**:

```java
// Cố ý không biên dịch:
Dog another = general.create("Luna");
```

Java không tự thu hẹp kiểu tĩnh của kết quả chỉ vì tại lúc chạy đối tượng factory là `DogFactory`.

Đây là điểm cần phân biệt:

- Kiểu tĩnh của biểu thức lời gọi được xác định khi biên dịch.
- Phần thực thi của phương thức instance phù hợp được chọn theo đối tượng thực tế khi chạy.
- Kiểu thực tế của đối tượng kết quả có thể cụ thể hơn kiểu tĩnh của biểu thức.

Cách xác định kiểu của lời gọi thuộc quy tắc tại [JLS §15.12.2.6](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12.2.6).

### Gọi phương thức ghi đè trên kết quả vẫn có đa hình

Biến `animal` có kiểu tĩnh `Animal`, nhưng chứa tham chiếu đến `Dog`. Lời gọi `animal.sound()` chạy phần thực thi của `Dog` và in `woof`.

Điều này không đòi hỏi biến `animal` phải đổi kiểu tĩnh thành `Dog`. Nó dùng cơ chế đa hình thông thường cho phương thức instance.

Ngược lại, `animal.fetch()` không biên dịch vì hợp đồng của kiểu tĩnh `Animal` không có `fetch`.

### Interface giữ hợp đồng tổng quát

`AnimalMaker` khai báo `Animal create(String name)`. Khi gọi qua biến `AnimalMaker`, kết quả tĩnh vẫn là `Animal`.

Đối tượng `specific` là `DogFactory`, nên kết quả thực tế của lời gọi qua interface vẫn là `Dog`. Hai dòng cuối của output kiểm chứng điều đó.

Kiểu trả về cụ thể hơn đem lại lợi ích cho người gọi qua kiểu cụ thể; nó không buộc mọi khách hàng của interface phải phụ thuộc `Dog`.

## Kiểu trả về không tạo nạp chồng

Java không cho phép tạo hai phương thức trong cùng lớp chỉ khác kiểu trả về:

```java
// Mảnh khai báo cố ý không hợp lệ khi cùng đặt trong một lớp:
Animal create(String name) { return new Animal(name); }
Dog create(String name) { return new Dog(name); }
```

Chữ ký cần phân biệt phương thức ở mã nguồn không chỉ dựa vào kiểu trả về theo cách này. Không thể yêu cầu trình biên dịch chọn một trong hai chỉ vì biến nhận kết quả là `Animal` hay `Dog`.

Trong ví dụ hợp lệ, hai khai báo nằm ở lớp cha và lớp con, có quan hệ ghi đè. Đó không phải hai overload chỉ khác kiểu trả về được người viết đặt cùng một lớp.

Nếu nhìn thấy qua reflection những phương thức có tên/tham số giống nhau nhưng kiểu trả về khác nhau, có thể có cầu nối do trình biên dịch sinh để hỗ trợ bản dịch. Điều đó không làm đoạn khai báo nguồn không hợp lệ phía trên trở thành hợp lệ.

## Ví dụ cố ý sai: đổi sang kiểu không liên quan

Lưu thành `BadReturnDemo.java`. Đây là một chương trình nguồn độc lập **cố ý không biên dịch**:

```java
public class BadReturnDemo {
    static class Base {
        public Number value() {
            return Integer.valueOf(1);
        }
    }

    static class Child extends Base {
        @Override
        public String value() {
            return "one";
        }
    }
}
```

Thử:

```shell
javac -encoding UTF-8 BadReturnDemo.java
```

Trình biên dịch từ chối vì `String` không thay thế được `Number` làm kiểu trả về của phương thức ghi đè. Câu chữ chẩn đoán phụ thuộc JDK/ngôn ngữ hiển thị; điều cần quan sát là quá trình biên dịch thất bại.

Nếu muốn giữ hợp đồng của `Base` nhưng cụ thể hóa kiểu kết quả, một lựa chọn về kiểu là `Integer`:

```java
// Mảnh thay thế phương thức Child.value() trong ví dụ:
@Override
public Integer value() {
    return Integer.valueOf(1);
}
```

Nếu thực sự cần trả chuỗi, phải xem lại thiết kế API hoặc dùng một phương thức có ý nghĩa khác. Xóa `@Override` không làm hai kiểu trả về không tương thích trở nên hợp lệ với cùng chữ ký.

## Những quy tắc ghi đè khác vẫn giữ nguyên

Kiểu trả về cụ thể hơn không cho phép bỏ qua các điều kiện khác:

| Điều kiện | Hệ quả |
| --- | --- |
| Phương thức cha là `public` | Phương thức ghi đè không được thu hẹp xuống protected hoặc package-private |
| Phương thức cha là `final` | Không được ghi đè |
| Phương thức là `static` | Cần phân biệt che khuất với ghi đè instance |
| Phương thức cha là `private` | Không được thừa kế để phương thức con ghi đè |
| Ngoại lệ được kiểm tra | Không được mở rộng hợp đồng throws trái quy tắc |
| Tham số phương thức | Vẫn phải thỏa quan hệ chữ ký ghi đè |

Trong ví dụ, các phương thức `create` là `public` vì hợp đồng của `AnimalMaker` yêu cầu mức truy cập đó. Việc trả `Dog` không làm một phương thức có quyền truy cập hẹp hơn trở nên hợp lệ.

Xem các yêu cầu tại [JLS §8.4.8.3](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.8.3).

## Không áp dụng đồng biến này cho kiểu nguyên thủy hoặc void

Nếu phương thức cha trả `int`, phương thức con không thể đổi thành `long`, dù một giá trị int có thể được mở rộng sang long trong ngữ cảnh khác.

Cũng không thể đổi `int` thành `Integer` rồi dựa vào boxing để xem là ghi đè hợp lệ.

`void` phải được giữ theo quy tắc tương ứng; không thể đổi từ `void` thành một kiểu tham chiếu để “trả thêm dữ liệu” bằng cơ chế đồng biến.

Bản chất ở đây là khả năng thay thế **kiểu trả về tham chiếu** trong hợp đồng ghi đè, không phải mọi chuyển đổi giá trị mà ngôn ngữ hỗ trợ.

## Generic: kiểu phần tử có quan hệ chưa đủ

Nếu `Dog extends Animal`, không được kết luận:

```text
List<Dog> la kieu con cua List<Animal>
```

Generic như `List<T>` không có quan hệ đồng biến kiểu phần tử theo cách đó. Vì vậy, phương thức cha trả `List<Animal>` không thể tùy ý được ghi đè bằng `List<Dog>` chỉ dựa trên quan hệ `Dog extends Animal`.

Một API có thể dùng wildcard để biểu diễn hợp đồng phù hợp, chẳng hạn `List<? extends Animal>`, nhưng đó là một quyết định thiết kế khác cần được kiểm tra theo các quy tắc generic.

Đừng sử dụng raw type hoặc unchecked cast chỉ để làm một khai báo trả về trông có vẻ tương thích. Nếu trình biên dịch đưa cảnh báo về generic, phải xem lại hợp đồng thay vì coi đó là cùng trường hợp đơn giản `Animal → Dog`.

## Đồng biến kiểu trả về không tự thực hiện chuyển đổi

Phương thức:

```java
@Override
public Dog create(String name) {
    return new Dog(name);
}
```

tự tạo một `Dog` trong phần thân. Quy tắc đồng biến chỉ cho phép chữ ký cụ thể hơn và kiểm tra giá trị trả về phải phù hợp.

Nó không:

- Biến một `Animal` đã có thành `Dog`.
- Sao chép thuộc tính từ đối tượng cha sang đối tượng con.
- Thêm tự động một phép downcast luôn an toàn.
- Bảo đảm kết quả khác `null`.
- Bảo đảm hành vi nghiệp vụ đúng với mọi kỳ vọng.

Một phương thức khai báo trả `Dog` vẫn có thể trả `null` về mặt kiểu tham chiếu. Nếu hợp đồng yêu cầu kết quả bắt buộc tồn tại, cần quy định và kiểm chứng riêng.

Tương tự, lớp con vẫn phải tôn trọng ý nghĩa hành vi của phương thức cha, chứ không chỉ làm kiểu trả về được trình biên dịch chấp nhận.

## Khi nào nên dùng?

Cơ chế này phù hợp khi một kiểu con có thể đưa ra cam kết kết quả cụ thể hơn một cách tự nhiên:

- Factory chuyên tạo một loại đối tượng.
- Phương thức tạo bản sao của một kiểu cụ thể.
- API chuỗi lời gọi cần trả đối tượng phù hợp với lớp con.
- Phần triển khai interface có kiểu kết quả cụ thể nhưng vẫn phục vụ hợp đồng chung.

Không nên tạo một hệ kế thừa chỉ để đổi kiểu trả về. Cần có quan hệ kiểu và hợp đồng có ý nghĩa trước; đồng biến là công cụ biểu đạt cam kết đó.

Với một API chuỗi lời gọi hoặc nhiều tầng generic, đôi khi cần một thiết kế generic riêng để giữ kiểu xuyên suốt. Một lần đổi kiểu trả về ở lớp con không tự giải quyết mọi vấn đề của toàn bộ cây kế thừa.

## Lỗi phổ biến và cách kiểm tra

| Hiểu nhầm | Cách kiểm tra |
| --- | --- |
| Lớp con muốn trả kiểu gì cũng được | Kiểm tra quan hệ kiểu con của kết quả |
| Đổi tham số cũng được xem là ghi đè | So sánh chữ ký và giữ @Override |
| Biến kiểu cha tự nhận kết quả tĩnh là Dog | Xem kiểu của biểu thức lời gọi tại lúc biên dịch |
| Đối tượng thực tế là Dog thì có thể gọi mọi phương thức Dog qua Animal | Kiểm tra thành viên trên kiểu tĩnh |
| Chỉ khác kiểu trả về là một overload hợp lệ | Nhớ quy tắc chữ ký nguồn |
| Boxing hoặc chuyển số cho phép đổi kiểu trả về nguyên thủy | Đây không phải quy tắc đồng biến tham chiếu |
| List<Dog> tự thay thế List<Animal> | Phân biệt generic với quan hệ kiểu phần tử |
| Trả Dog là bảo đảm khác null và đúng nghiệp vụ | Kiểm tra hợp đồng dữ liệu/hành vi riêng |

## Thực hành kiểm chứng

1. Chạy chương trình và giải thích tại sao cả hai đường qua kiểu cha/interface vẫn tạo `Dog`.
2. Đổi chữ ký phương thức ở `DogFactory` về trả `Animal`, giữ `return new Dog(name)`. Quan sát dòng gán trực tiếp kết quả cho biến `Dog` không còn biên dịch: phần thân cụ thể hơn không tự thay chữ ký công khai.
3. Khôi phục, rồi thử gán `general.create("Luna")` thẳng vào biến `Dog`; giải thích lỗi dựa trên kiểu tĩnh.
4. Trong ví dụ cố ý sai, đổi `String` thành `Integer` và trả giá trị phù hợp để xác nhận quan hệ kiểu trả về hợp lệ.
5. Thêm một kiểu con khác của `Animal` và một factory chuyên biệt; giữ hợp đồng `AnimalMaker` để so sánh sự tổng quát của interface với cam kết cụ thể của từng lớp.

Điều cần nắm là **phương thức ghi đè có thể thu hẹp cam kết kiểu kết quả tham chiếu**, còn người gọi nhìn thấy cam kết nào phụ thuộc kiểu khai báo mà họ đang sử dụng.
