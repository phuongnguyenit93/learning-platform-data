# Ép kiểu tham chiếu, `instanceof` và `ClassCastException` trong Java

> **Java core — language-basics / Chuyển đổi kiểu**  
> **Yêu cầu:** JDK 17+; một tệp Java độc lập, không cần thư viện ngoài.  
> **Mục tiêu:** Phân biệt *upcasting* và *downcasting* tham chiếu, hiểu **kiểu khai báo** và **kiểu thực tế** của đối tượng, kiểm tra bằng `instanceof` (bao gồm *pattern matching* Java 17), và nhận diện/né tránh `ClassCastException` khi ép kiểu không hợp lệ lúc chạy.

## 1. Ép kiểu tham chiếu không biến đối tượng thành đối tượng khác

Xét hệ phân cấp:

~~~java
abstract class Animal {
    abstract String sound();
}
class Dog extends Animal {
    @Override String sound() { return "woof"; }
    void fetch() { /* chỉ Dog có hành vi này */ }
}
class Cat extends Animal {
    @Override String sound() { return "meow"; }
}
~~~

Một biến kiểu `Animal` có thể tham chiếu một đối tượng thật sự thuộc `Dog`:

~~~java
Animal pet = new Dog(); // Upcast ngầm từ Dog lên Animal.
~~~

Phân biệt rõ hai khái niệm:

- **Kiểu khai báo / static type:** `Animal` là kiểu compiler nhìn thấy cho biến `pet`. Vì vậy gọi `pet.sound()` được, nhưng `pet.fetch()` **không** biên dịch vì `Animal` không khai báo phương thức `fetch()`.
- **Kiểu thực tế / runtime class:** object mà `pet` trỏ đến vẫn là một `Dog`. Java dispatch `pet.sound()` tới bản ghi đè của `Dog`.
- **Ép kiểu tham chiếu:** thay cách compiler xem một tham chiếu theo quan hệ kiểu cho phép; **không tạo, sao chép, thay class hoặc thay dữ liệu** của object.

Nếu cần phương thức riêng của `Dog` và biết chắc object thật sự là Dog:

~~~java
Dog dog = (Dog) pet; // Downcast tường minh.
dog.fetch();
~~~

Sau cast, `pet` và `dog` vẫn trỏ tới **cùng object Dog**. Việc ép kiểu này không giống `Integer.parseInt` hay chuyển đổi chuỗi thành số: nó không chuyển dữ liệu bên trong đối tượng.

## 2. Upcast và downcast khác nhau thế nào?

| Trường hợp | Ví dụ | Có cần cast tường minh? | Kiểm tra lúc chạy |
| --- | --- | --- | --- |
| **Upcast** lớp con → lớp cha | `Animal a = new Dog();` | Không | An toàn theo quan hệ kế thừa |
| Upcast đến interface được thực thi | `Runnable r = new Thread();` | Không | An toàn theo quan hệ implements |
| **Downcast** cha → con | `Dog d = (Dog) a;` | Có | Object thực tế phải tương thích với Dog |
| Từ `Object` → lớp cụ thể | `String s = (String) obj;` | Có | Object thực tế phải là String (hoặc subtype phù hợp) |
| Cast `null` sang kiểu tham chiếu | `Dog d = (Dog) null;` | Có thể viết | Kết quả vẫn là `null`, **không ném `ClassCastException`** |

Cast từ kiểu cha xuống kiểu con **có thể biên dịch** mà vẫn lỗi lúc chạy. Compiler chỉ chứng minh phép chuyển đổi *có thể* có ý nghĩa, không biết chắc runtime class của mọi object biến đó có thể trỏ tới.

Ví dụ:

~~~java
Animal pet = new Cat();
// Dog wrong = (Dog) pet; // Nếu chạy: ClassCastException.
~~~

`Cat` là một `Animal`, **không** phải một `Dog`; ép tham chiếu sang Dog không thể thay đổi sự thật đó.

Ở chiều ngược lại, một số phép ép giữa các lớp hoàn toàn không có quan hệ chuyển kiểu khả dĩ bị **từ chối ngay tại thời điểm biên dịch**, thay vì đợi đến `ClassCastException`. Không phải mọi cú pháp `(Type) value` đều hợp lệ.

## 3. `instanceof` kiểm tra kiểu runtime trước khi downcast

Toán tử `instanceof` hỏi liệu object thật sự được tham chiếu có tương thích với kiểu được kiểm tra hay không:

~~~java
Animal pet = new Dog();

System.out.println(pet instanceof Dog); // true
System.out.println(pet instanceof Cat); // false
System.out.println(pet instanceof Animal); // true
~~~

**Java 17** hỗ trợ *pattern matching for instanceof*, gộp kiểm tra với khai báo biến đã được thu hẹp kiểu:

~~~java
if (pet instanceof Dog dog) {
    dog.fetch(); // Compiler biết dog có kiểu Dog.
}
~~~

Điều này rõ ràng hơn mẫu cũ:

~~~java
if (pet instanceof Dog) {
    Dog dog = (Dog) pet;
    dog.fetch();
}
~~~

Phạm vi của **pattern variable** phụ thuộc luồng điều khiển: trong khối `if` trên, `dog` chỉ dùng được tại nhánh mà kiểm tra chắc chắn thành công. Đừng dùng tên đó bên ngoài vị trí compiler bảo đảm đã được gán.

**Lưu ý về `null`:** `null instanceof Dog` và `variableNull instanceof Dog` đều cho **`false`**; cú pháp `instanceof` không gây NPE chỉ vì toán hạng trái bằng `null`. Nếu một tham chiếu `null` được ép sang kiểu tham chiếu hợp lệ, kết quả vẫn là `null`; lỗi NPE chỉ có thể xảy ra **khi sau đó cố sử dụng nó như một object**.

## 4. Chương trình Java 17+ có thể biên dịch và chạy

Tạo tệp **ReferenceCastDemo.java**:

~~~java
public final class ReferenceCastDemo {
    private abstract static class Animal {
        private final String name;

        Animal(String name) {
            this.name = name;
        }

        String name() {
            return name;
        }

        abstract String sound();
    }

    private static final class Dog extends Animal {
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

    private static final class Cat extends Animal {
        Cat(String name) {
            super(name);
        }

        @Override
        String sound() {
            return "meow";
        }
    }

    private static String describe(Animal animal) {
        if (animal instanceof Dog dog) {
            return "dog:" + dog.name();
        }
        if (animal instanceof Cat cat) {
            return "cat:" + cat.name();
        }
        return "none";
    }

    public static void main(String[] args) {
        Animal pet = new Dog("Milo"); // Upcast.
        System.out.println("runtimeType="
                + pet.getClass().getSimpleName());
        System.out.println("polymorphicSound=" + pet.sound());
        System.out.println("isDog=" + (pet instanceof Dog));
        System.out.println("isCat=" + (pet instanceof Cat));

        Dog dog = (Dog) pet; // Downcast hợp lệ.
        System.out.println("sameObject=" + (pet == dog));
        System.out.println("fetch=" + dog.fetch());
        System.out.println("describeDog=" + describe(pet));

        Animal another = new Cat("Luna");
        System.out.println("catSound=" + another.sound());
        System.out.println("describeCat=" + describe(another));

        try {
            Dog wrong = (Dog) another; // Runtime là Cat.
            System.out.println(wrong.fetch());
        } catch (ClassCastException ex) {
            System.out.println("animalCastFailed=true");
        }

        Object number = Integer.valueOf(7);
        System.out.println("objectIsString="
                + (number instanceof String));
        try {
            String wrong = (String) number;
            System.out.println("unexpected=" + wrong);
        } catch (ClassCastException ex) {
            System.out.println("objectCastFailed=true");
        }

        Animal absent = null;
        System.out.println("nullInstanceof=" + (absent instanceof Dog));
        Dog nullDog = (Dog) absent; // Cast null tham chiếu hợp lệ.
        System.out.println("nullCast=" + (nullDog == null));
        System.out.println("describeNull=" + describe(absent));
    }
}
~~~

Mở terminal tại thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 ReferenceCastDemo.java
java ReferenceCastDemo
~~~

**Expected output chính xác:**

~~~text
runtimeType=Dog
polymorphicSound=woof
isDog=true
isCat=false
sameObject=true
fetch=Milo fetched
describeDog=dog:Milo
catSound=meow
describeCat=cat:Luna
animalCastFailed=true
objectIsString=false
objectCastFailed=true
nullInstanceof=false
nullCast=true
describeNull=none
~~~

Giải thích:

1. `pet` khai báo `Animal` nhưng runtime class là `Dog`; gọi `pet.sound()` chạy phiên bản `Dog.sound()` nhờ đa hình.
2. `(Dog) pet` thành công và `pet == dog` là `true` vì cast **không tạo object mới**.
3. `describe` dùng pattern matching `instanceof` để kiểm tra kiểu và có sẵn biến `dog`/`cat` đúng kiểu mà không cần cast riêng.
4. `(Dog) another` biên dịch vì biến `another` có kiểu `Animal`, nhưng runtime là `Cat` nên ném `ClassCastException`.
5. `number` thật sự chứa `Integer`. `number instanceof String` cho false; `(String) number` ném `ClassCastException`.
6. `absent` bằng `null`: `instanceof` cho false, cast sang `Dog` vẫn nhận `null`. Truy cập phương thức qua tham chiếu ấy mới có nguy cơ gây `NullPointerException`.

Các khối `catch` dùng **duy nhất để minh họa lỗi kiểm tra runtime**; trong code sản xuất, ưu tiên kiểm tra, thiết kế API hoặc đa hình phù hợp thay vì dùng exception làm điều kiện phân nhánh thường xuyên.

## 5. Phân biệt `ClassCastException` và những lỗi gần giống

| Hiện tượng | Loại lỗi / hành vi | Lý do |
| --- | --- | --- |
| `Animal x = new Cat(); Dog d = (Dog) x;` | **ClassCastException** lúc chạy | Object runtime là Cat, không phải Dog |
| `Object x = Integer.valueOf(7); String s = (String) x;` | **ClassCastException** lúc chạy | Integer không thể xem là String |
| `Dog d = (Dog) null;` | Thành công, `d == null` | Cast null không phát sinh ClassCastException |
| `d.fetch()` khi `d == null` | **NullPointerException** | Gọi method trên tham chiếu null |
| `Animal a = new Dog(); a.fetch();` | **Lỗi biên dịch** | Kiểu khai báo Animal không có `fetch()` |
| `String s = (String) new Dog(...);` với lớp không liên quan | **Lỗi biên dịch** | Không tồn tại cast được Java chấp nhận giữa hai kiểu lớp đó |
| Gán `Dog[]` cho `Animal[]` rồi lưu một `Cat` | Có thể **ArrayStoreException** | Runtime kiểm tra loại phần tử mảng, không phải phép ép tham chiếu trực tiếp |

`ClassCastException` phản ánh **một tham chiếu không tương thích với kiểu mà chương trình muốn ép**; NPE nói rằng không có object tại tham chiếu được sử dụng. Hai lỗi có nguyên nhân và cách sửa khác nhau.

## 6. Khi nào nên cast, khi nào tránh cast?

**Ưu tiên đa hình** nếu hành vi có thể được mô tả bởi kiểu cha hoặc interface:

~~~java
Animal pet = new Dog("Milo");
System.out.println(pet.sound()); // Không cần biết subtype.
~~~

Chỉ downcast khi thật sự cần API đặc thù của subtype và điều kiện tương thích được kiểm tra:

~~~java
if (pet instanceof Dog dog) {
    System.out.println(dog.fetch());
}
~~~

Một số nguyên tắc:

- **Dựa vào hợp đồng kiểu:** API trả `Animal` không có nghĩa đối tượng luôn là `Dog`. Đừng cast chỉ vì “test thử thấy chạy”.
- **Không bắt `ClassCastException` để thay thế `instanceof`** trong luồng bình thường; bắt exception phù hợp khi xử lý lỗi bất thường hoặc ở ranh giới cần kiểm soát lỗi.
- **Dùng pattern matching đúng mức:** `instanceof Dog dog` gọn hơn kiểm tra rồi cast lặp, nhưng dùng lạm dụng nhiều điều kiện subtype có thể báo hiệu thiết kế cần đa hình/strategy.
- **Đừng nhầm cast với chuyển đổi giá trị:** `(String) Integer.valueOf(7)` không phải cách biến số thành chuỗi; dùng `String.valueOf(7)` nếu thật sự muốn chuyển nội dung.
- **Lưu ý generic type erasure:** không thể dùng `obj instanceof java.util.List<String>` để kiểm tra đầy đủ tham số kiểu ở runtime; việc kiểm tra `instanceof List<?>` chỉ xác nhận lớp/kiểu gốc, không xác nhận mọi phần tử là String.

## 7. Bài tập tự luyện

**Bài 1.** Cho `Animal a = new Dog("Max");`. Tại sao `a.sound()` hợp lệ còn `a.fetch()` không biên dịch? Viết một cách gọi `fetch()` an toàn.

**Bài 2.** Cho `Animal animal = new Cat("Miu");`. Dự đoán `animal instanceof Dog` và hành vi của `(Dog) animal`; chỉ ra thời điểm lỗi xảy ra.

**Bài 3.** Thay `Animal animal = null;` trong phép kiểm tra `instanceof`. Kết quả là gì? Vì sao `(Dog) animal` tự nó không phát sinh NPE hoặc ClassCastException?

**Bài 4.** Cho `Object obj = Integer.valueOf(5);`. So sánh hành vi `obj instanceof String`, `(String) obj` và `String.valueOf(obj)`.

**Bài 5.** Sửa hàm `describe` trong chương trình để dùng mẫu `instanceof` cho subtype; nếu truyền object là Dog, Cat hoặc null, kết quả in ra phải tương ứng.

### Ghi nhớ

**Ép kiểu tham chiếu thay đổi cách nhìn kiểu của biến, không thay đổi object.** Upcast thường an toàn và không cần cast. Downcast yêu cầu object runtime tương thích, nếu không sẽ ném **`ClassCastException`**. Dùng **`instanceof`** hoặc pattern matching Java 17 để kiểm tra khi cần API của subtype, nhớ rằng **`null instanceof Type` là false** và **cast null tham chiếu vẫn cho null**. Khi chỉ cần hành vi chung, hãy ưu tiên **đa hình** thay vì cast.
