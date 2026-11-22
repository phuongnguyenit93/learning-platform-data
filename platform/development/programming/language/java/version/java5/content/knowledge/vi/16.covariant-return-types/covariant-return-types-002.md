# Quan hệ kiểu con trong kiểu trả về của phương thức

## 1. Đồng biến ở kiểu trả về nghĩa là gì?

Giả sử một API hứa phương thức `duplicate()` trả về Document. Một lớp Invoice là kiểu con của Document có thể hứa cụ thể hơn: phương thức ghi đè trả về Invoice.

Điều này hợp lý vì mọi Invoice đều dùng được ở nơi yêu cầu Document. Bên gọi dựa vào hợp đồng Document vẫn nhận được một Document hợp lệ; bên gọi biết Invoice có thêm thông tin kiểu ngay khi biên dịch.

```text
Invoice là kiểu con của Document

Hợp đồng cha:       Document duplicate()
Khai báo ghi đè:    Invoice  duplicate()
```

Đây là **kiểu trả về đồng biến (covariant return type)**. Trong trường hợp kiểu tham chiếu thông thường, kiểu trả về của phương thức ghi đè được giữ nguyên hoặc thu hẹp thành kiểu con tương thích với kiểu trả về của phương thức cha. [JLS: kết quả phương thức](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.5)

“Thu hẹp” ở đây nói về tập giá trị được hứa trả về, không phải thu hẹp quyền truy cập. Phương thức con vẫn phải tuân thủ các quy tắc ghi đè khác.

## 2. Vì sao bên gọi vẫn dùng được kết quả?

Nếu bên gọi yêu cầu một Document, kết quả là Invoice vẫn có các khả năng mà Document công bố. Vì vậy việc dùng một lớp con làm kiểu trả về không làm mất cam kết kiểu của phương thức cha.

Chiều ngược lại không đúng: nếu phương thức cha hứa Invoice mà phương thức con trả Document, một Document bất kỳ chưa chắc là Invoice. Trình biên dịch phải từ chối việc mở rộng kiểu trả về như vậy.

| Kiểu trả về cha | Kiểu trả về con | Hợp lệ trong trường hợp tham chiếu tương ứng? |
| --- | --- | --- |
| `Object` | `String` | Có |
| `Number` | `Integer` | Có |
| `Document` | `Invoice extends Document` | Có |
| `Invoice` | `Document` | Không |
| `String` | `Integer` | Không |
| `Document` | `Document` | Có, giữ nguyên kiểu |

Cần kiểm tra quan hệ **kiểu con (subtype)**, không chỉ việc hai kiểu “có liên quan” trong nghiệp vụ. Hai lớp đều cùng kế thừa Object không khiến chúng thay thế được cho nhau ở một kiểu trả về cụ thể. [JLS: quan hệ kiểu con của lớp và interface](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.10.2)

## 3. Ví dụ chạy được: kiểu cha và kiểu con tại bên gọi

Lưu toàn bộ vào **CovariantReturnDemo.java**:

```java
public class CovariantReturnDemo {
    static class Document {
        private final String title;

        Document(String title) {
            this.title = title;
        }

        public String title() {
            return title;
        }

        public Document duplicate() {
            return new Document(title);
        }
    }

    static class Invoice extends Document {
        private final int total;

        Invoice(String title, int total) {
            super(title);
            this.total = total;
        }

        public int total() {
            return total;
        }

        @Override
        public Invoice duplicate() {
            return new Invoice(title(), total);
        }
    }

    public static void main(String[] args) {
        Invoice original = new Invoice("October", 120);

        Invoice specific = original.duplicate();
        System.out.println("specificTotal=" + specific.total());
        System.out.println("specificTitle=" + specific.title());

        Document general = original;
        Document result = general.duplicate();

        System.out.println("runtimeType="
                + result.getClass().getSimpleName());
        System.out.println("newInstance=" + (result != original));

        if (result instanceof Invoice invoice) {
            System.out.println("checkedTotal=" + invoice.total());
        }

        System.out.println("baseCall=" + selected(general.duplicate()));
        System.out.println("specificCall="
                + selected(original.duplicate()));
    }

    private static String selected(Document value) {
        return "Document";
    }

    private static String selected(Invoice value) {
        return "Invoice";
    }
}
```

Biên dịch và chạy bằng JDK hỗ trợ Java 17:

```shell
javac --release 17 -encoding UTF-8 CovariantReturnDemo.java
java CovariantReturnDemo
```

Kết quả:

```text
specificTotal=120
specificTitle=October
runtimeType=Invoice
newInstance=true
checkedTotal=120
baseCall=Document
specificCall=Invoice
```

### Hai loại thông tin kiểu trong cùng lời gọi

Ở `original.duplicate()`, biến original có kiểu tĩnh Invoice. Trình biên dịch thấy phương thức trả Invoice, nên có thể gán trực tiếp vào biến Invoice và gọi `total()` mà không ép kiểu.

Ở `general.duplicate()`, biến general có kiểu tĩnh Document. Việc chọn thân phương thức lúc chạy vẫn đi đến `Invoice.duplicate()` vì đối tượng thực tế là Invoice. Nhưng kiểu của biểu thức ở bên gọi vẫn theo hợp đồng Document đã biết lúc biên dịch.

Do đó dòng sau, nếu thêm vào `main`, không biên dịch:

```java
Invoice wrong = general.duplicate();
```

Đây là đoạn cố ý không hợp lệ. Kết quả thực tế trong ví dụ là Invoice không làm trình biên dịch tự thu hẹp hợp đồng của một biến Document. Muốn dùng khả năng riêng của Invoice khi chỉ có một Document, cần có bằng chứng kiểu, chẳng hạn `instanceof` như trong chương trình.

Hai dòng cuối dùng nạp chồng để quan sát kiểu tĩnh của biểu thức: `selected(Document)` được chọn cho `general.duplicate()`, còn `selected(Invoice)` được chọn cho `original.duplicate()`. Chúng không làm thay đổi quy tắc chọn phương thức ghi đè lúc chạy.

## 4. Kiểu trả về khai báo khác với giá trị trả về cụ thể

Đoạn khai báo sau cũng hợp lệ:

```java
class Parent {
    public Number number() {
        return Integer.valueOf(1);
    }
}
```

Phương thức khai báo trả Number nhưng tạo Integer trong thân. Đây chưa phải một ví dụ ghi đè có kiểu trả về đồng biến, vì chưa có phương thức con nào đổi kiểu khai báo.

Đồng biến xuất hiện khi một phương thức ghi đè thay **kiểu trả về trong khai báo**, chẳng hạn Number → Integer. Chỉ đổi câu lệnh `return` trong thân mà vẫn khai báo Number không làm bên gọi nhận kiểu tĩnh Integer.

Khai báo kiểu trả về cụ thể hơn cũng không tự bảo đảm kết quả khác null. Nếu hợp đồng yêu cầu không null hoặc dữ liệu phải thỏa điều kiện nghiệp vụ, tác giả vẫn phải thực hiện cam kết đó trong thân phương thức.

## 5. Áp dụng khi triển khai interface

Quan hệ này không chỉ dùng với lớp cha cụ thể. Một lớp triển khai interface có thể cung cấp phương thức với kiểu trả về là kiểu con phù hợp của kiểu đã công bố.

Ví dụ khai báo độc lập sau không có `main`:

```java
interface Product {
}

class Report implements Product {
}

interface ProductFactory {
    Product create();
}

class ReportFactory implements ProductFactory {
    @Override
    public Report create() {
        return new Report();
    }
}
```

Report là một Product, nên `ReportFactory.create()` đáp ứng hợp đồng. Bên gọi có kiểu ReportFactory biết ngay kết quả Report; bên gọi qua ProductFactory vẫn nhìn thấy Product.

Nếu triển khai phương thức interface public, phải giữ public ở phương thức lớp. Việc thu hẹp kiểu trả về không cho phép giảm quyền truy cập. [JLS: ghi đè phương thức interface](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.4.1)

## 6. Generic: phải xét quan hệ kiểu của toàn bộ kết quả

Dog là kiểu con của Animal không làm `List<Dog>` trở thành kiểu con của `List<Animal>`. Vì vậy phương thức cha trả `List<Animal>` không cho phép phương thức con ghi đè bằng `List<Dog>` chỉ dựa vào quan hệ Dog → Animal.

Ngược lại, `ArrayList<Animal>` là kiểu con của `List<Animal>`, nên quan hệ này có thể dùng làm kiểu trả về đồng biến.

Một hợp đồng `List<? extends Animal>` cũng có thể được đáp ứng bằng `List<Dog>`, vì quan hệ kiểu ở đây khác với `List<Animal>`. Cần chọn wildcard theo nhu cầu API, không chỉ để làm một phép ghi đè hết lỗi.

### Chương trình kiểm chứng với wildcard

Lưu thành **GenericCovariantReturnDemo.java**:

```java
import java.util.List;

public class GenericCovariantReturnDemo {
    static class Animal {
        public String kind() {
            return "animal";
        }
    }

    static class Dog extends Animal {
        @Override
        public String kind() {
            return "dog";
        }

        public String bark() {
            return "woof";
        }
    }

    interface AnimalSource {
        List<? extends Animal> animals();
    }

    static class DogSource implements AnimalSource {
        @Override
        public List<Dog> animals() {
            return List.of(new Dog());
        }
    }

    public static void main(String[] args) {
        DogSource specific = new DogSource();
        List<Dog> dogs = specific.animals();
        System.out.println("specific=" + dogs.get(0).bark());

        AnimalSource general = specific;
        List<? extends Animal> animals = general.animals();
        System.out.println("general=" + animals.get(0).kind());
    }
}
```

Chạy:

```shell
javac --release 17 -encoding UTF-8 GenericCovariantReturnDemo.java
java GenericCovariantReturnDemo
```

Kết quả:

```text
specific=woof
general=dog
```

Ở bên gọi qua AnimalSource, phần tử được sử dụng an toàn như Animal. Wildcard này không hứa danh sách chấp nhận thêm một Animal bất kỳ. Nếu hợp đồng cần thêm phần tử, phải thiết kế lại theo nhu cầu đó. [JLS: kiểu tham số hóa và quan hệ kiểu con](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.10.2)

## 7. Các giới hạn khi áp dụng quy tắc

### Không đổi kiểu nguyên thủy bằng phép mở rộng số

Nếu cha trả `int`, con không thể đổi thành `long`, dù Java cho gán một giá trị int vào biến long trong tình huống khác. Phương thức trả kiểu nguyên thủy phải giữ kiểu trả về phù hợp theo quy tắc riêng của ghi đè, không dùng chuyển đổi số để thay thế.

Tương tự:

- `int` không đổi thành `Integer` nhờ boxing.
- `Integer` không đổi thành `int` nhờ unboxing.
- `void` không đổi thành một kiểu có giá trị, và chiều ngược lại cũng không hợp lệ.

### Không đổi tham số để tạo “ghi đè đồng biến”

Phương thức cha `void accept(Animal value)` và phương thức con `void accept(Dog value)` không có cùng danh sách kiểu tham số để ghi đè trực tiếp. Chúng là trường hợp nạp chồng theo chữ ký tương ứng, không phải cơ chế đồng biến kiểu trả về.

Đổi một phương thức từ `Document duplicate()` thành `Invoice duplicate(int copies)` cũng tạo phương thức khác. Việc Invoice là kiểu con không bù được thay đổi tham số.

### Không phân biệt phương thức chỉ bằng kiểu trả về

Trong cùng một lớp, không được khai báo cả `Document duplicate()` và `Invoice duplicate()` như hai overload độc lập chỉ khác kiểu trả về. Quy tắc ghi đè ở lớp con không biến kiểu trả về thành một phần phân biệt overload trong cùng lớp. [JLS: chữ ký phương thức](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.2)

### Còn phải đáp ứng hợp đồng ghi đè

Các giới hạn khác vẫn giữ: không giảm quyền truy cập, không ghi đè phương thức final và không mở rộng checked exception tùy ý. Phương thức static không có cơ chế phân phối động như phương thức instance; đừng dùng ví dụ static để suy ra hành vi trong chương trình đầu. [JLS: yêu cầu khi ghi đè](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.8.3)

Nên dùng `@Override` khi có ý định ghi đè. Nó giúp trình biên dịch phát hiện thay đổi chữ ký ngoài ý muốn, chẳng hạn thu hẹp tham số thành một overload. [API Override](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Override.html)

## 8. Khi nào kiểu trả về cụ thể hơn hữu ích?

Nó hữu ích khi lớp con thực sự bảo đảm một kết quả chuyên biệt: nhà máy trả đúng loại sản phẩm, thao tác tạo bản sao giữ loại đối tượng, hoặc API nối lời gọi muốn tiếp tục dùng khả năng của lớp con.

Lợi ích là bên gọi biết lớp con không cần ép kiểu chỉ để khôi phục thông tin mà chính phương thức đã bảo đảm. Tuy nhiên, nếu bên gọi chỉ cần hợp đồng chung, vẫn nên dùng kiểu chung phù hợp; đồng biến không bắt buộc mọi nơi phải phụ thuộc lớp triển khai.

Khi xem một thiết kế, hãy kiểm tra theo thứ tự:

1. Đây có thật sự là phương thức ghi đè hoặc triển khai không?
2. Kiểu trả về con có dùng được ở nơi yêu cầu kiểu trả về cha không?
3. Bên gọi đang nhìn qua kiểu tĩnh nào?
4. Có generic, kiểu nguyên thủy hoặc quy tắc ghi đè khác cần xét không?
5. Thân phương thức có giữ các cam kết nghiệp vụ ngoài kiểu dữ liệu không?

### Tự thực hành

1. Trong chương trình đầu, đổi khai báo `Invoice.duplicate()` thành trả Document nhưng vẫn tạo Invoice. Dòng nào trong main không còn biên dịch?
2. Đổi phương thức cha thành trả Invoice nhưng phương thức con trả Document. Vì sao chiều quan hệ này không hợp lệ?
3. Trong chương trình generic, đổi interface thành `List<Animal> animals()` nhưng giữ lớp triển khai trả `List<Dog>`. Kiểm tra lỗi và giải thích quan hệ kiểu của hai List.
4. Thêm phương thức `duplicate(String suffix)` ở Invoice với `@Override`. Vì sao compiler báo lỗi nếu cha không có chữ ký đó?
5. Tạo interface nhà máy trả Product và lớp triển khai trả Report; đối chiếu kiểu kết quả khi gọi qua từng kiểu biến.
