# Nhận diện annotation `@Override` và `@Deprecated` trong Java

> **Java core — language-basics / Lớp và đối tượng**  
> **Môi trường:** Java 17+, chỉ cần JDK.  
> **Mục tiêu:** Biết mục đích, vị trí và tác dụng của `@Override`, `@Deprecated`; phân biệt ghi đè với nạp chồng/che khuất phương thức; nhận diện API cũ và cách thay thế an toàn.

## 1. Annotation là gì?

*Annotation* là thông tin bổ sung được đặt trên khai báo (và một số vị trí khác tùy loại annotation), thường bắt đầu bằng dấu `@`. Nó giúp trình biên dịch, công cụ hoặc thư viện nhận biết ý định của mã:

~~~java
@Override
public String toString() {
    return "example";
}
~~~

Annotation **không phải** lời gọi phương thức. Đặt `@Override` trước khai báo phương thức không làm thân tự chạy; phương thức vẫn chạy khi được gọi theo quy tắc Java.

| Annotation | Ý nghĩa chính | Tác dụng dễ quan sát |
| --- | --- | --- |
| `@Override` | Khai báo này dự định ghi đè/triển khai một phương thức hợp lệ từ lớp cha/interface | Trình biên dịch báo lỗi nếu thực tế không ghi đè/triển khai đúng |
| `@Deprecated` | API đã không còn được khuyến nghị sử dụng | Công cụ/trình biên dịch có thể cảnh báo khi mã khác dùng API cũ |

Hai annotation này nằm trong `java.lang` nên không cần `import`. Không nhầm `@Deprecated` với một lệnh xóa mã và không nhầm `@Override` với từ khóa bắt buộc để Java có đa hình.

## 2. `@Override` trên phương thức ghi đè từ lớp cha

~~~java
class Animal {
    public String speak() {
        return "generic";
    }
}

class Dog extends Animal {
    @Override
    public String speak() {
        return "woof";
    }
}
~~~

`Dog.speak()` ghi đè `Animal.speak()`: cùng tên và danh sách kiểu tham số, kiểu trả về tương thích và đáp ứng các quy tắc về quyền truy cập/ngoại lệ. Gọi qua tham chiếu kiểu cha vẫn thực thi phiên bản ở đối tượng thực:

~~~java
Animal pet = new Dog();
System.out.println(pet.speak()); // woof
~~~

`@Override` yêu cầu compiler kiểm tra ý định này. Nếu vô tình viết `speek()` thay `speak()` rồi vẫn gắn `@Override`, trình biên dịch báo lỗi thay vì âm thầm tạo một phương thức **mới**.

**Không có `@Override` thì ghi đè hợp lệ vẫn xảy ra**, nhưng thêm annotation giúp phát hiện sai chữ ký sớm và làm mã rõ hơn.

Có thể ghi đè các phương thức instance phù hợp của `Object`, chẳng hạn `toString()`:

~~~java
@Override
public String toString() {
    return "Dog";
}
~~~

## 3. `@Override` khi triển khai interface

Một lớp triển khai interface thường ghi `@Override` trước phương thức hiện thực hóa hợp đồng:

~~~java
interface Audible {
    String sound();
}

class Bird implements Audible {
    @Override
    public String sound() {
        return "chirp";
    }
}
~~~

`Bird.sound()` phải đáp ứng chữ ký và kiểu trả về của `Audible.sound()`. Vì phương thức trong interface ở ví dụ này là `public`, phương thức triển khai cũng phải `public`; không được làm giảm quyền truy cập.

Trong Java 17, `@Override` cũng được dùng khi ghi đè một `default method` phù hợp của interface. Annotation không tự thay thế từ khóa `implements`/`extends`: quan hệ kiểu và định nghĩa phương thức phải có sẵn.

## 4. Những trường hợp `@Override` không hợp lệ

| Tình huống | Có phải ghi đè hợp lệ để dùng `@Override`? | Lý do |
| --- | --- | --- |
| Viết sai tên `speek()` thay `speak()` | Không | Không khớp phương thức cha |
| `speak(int n)` trong khi cha chỉ có `speak()` | Không | Đây là **overload**, danh sách tham số khác |
| Định nghĩa một phương thức mới chỉ có trong lớp con | Không | Không có phương thức phù hợp để ghi đè |
| Viết constructor `Dog()` | Không | Constructor không phải phương thức ghi đè |
| Khai báo `static` trùng với static method cha | Không | Đây là **method hiding**, không phải overriding |
| Cố ghi đè phương thức `private` của cha | Không | Phương thức private không được kế thừa để ghi đè |
| Cố ghi đè phương thức `final` của cha | Không | `final` chặn việc ghi đè |

Ví dụ dưới đây **cố ý không biên dịch**, chỉ dùng để nhận diện lỗi:

~~~java
class Parent {
    public void run() {}
}

class Child extends Parent {
    // @Override
    // public void run(int times) {} // Lỗi: chỉ nạp chồng, không ghi đè.

    // @Override
    // public void rnu() {} // Lỗi: gõ sai tên phương thức.
}
~~~

Bỏ comment `@Override` trong một ví dụ sai sẽ khiến lỗi được phát hiện ngay khi biên dịch. Đừng bỏ annotation chỉ để che lỗi: hãy xem tên, kiểu tham số, kiểu trả về và quan hệ kế thừa/triển khai.

`@Override` cũng không biến lời gọi static thành đa hình. Sự phân giải **overload** dựa vào kiểu biểu thức tại thời điểm biên dịch, trong khi **overriding** của phương thức instance hỗ trợ dispatch theo đối tượng thực lúc chạy.

## 5. `@Deprecated`: đánh dấu API cũ, chưa phải xóa API

~~~java
class LabelService {
    /**
     * @deprecated Use modernLabel(String) instead.
     */
    @Deprecated(since = "17", forRemoval = false)
    public String oldLabel(String value) {
        return "old:" + value;
    }

    public String modernLabel(String value) {
        return "new:" + value;
    }
}
~~~

Dù phương thức `oldLabel` đã được gắn `@Deprecated`, lời gọi vẫn có thể biên dịch và chạy khi API đó còn tồn tại:

~~~java
LabelService service = new LabelService();
System.out.println(service.modernLabel("Java")); // new:Java
System.out.println(service.oldLabel("Java"));    // old:Java
~~~

Trình biên dịch/công cụ có thể báo cảnh báo về cách dùng API deprecated; cảnh báo **không đồng nghĩa lỗi biên dịch**, và annotation không tự làm phương thức bị gỡ khỏi class.

Có thể đánh dấu deprecated cho **class**, **constructor**, **method**, **field** và các loại khai báo mà annotation cho phép. Vì người dùng API cần biết đường thay thế, nên viết tài liệu migration rõ ràng.

**Hai phần khác nhau:**

- `@Deprecated` là **annotation** có ý nghĩa được trình biên dịch/công cụ nhận biết.
- `@deprecated` viết thường trong `/** ... */` là **Javadoc tag**, để giải thích lý do và gợi ý API thay thế cho người đọc tài liệu.

Nên dùng **cả hai** khi xuất bản API cũ. Chỉ viết Javadoc `@deprecated` mà thiếu annotation sẽ không cung cấp đầy đủ tín hiệu deprecated chuẩn cho công cụ.

## 6. `since`, `forRemoval` và xử lý cảnh báo

Từ Java 9, `@Deprecated` có hai thành phần tùy chọn, đều dùng được trên Java 17:

| Cú pháp | Diễn giải |
| --- | --- |
| `@Deprecated` | Đánh dấu deprecated, không khai báo thêm thông tin |
| `@Deprecated(since = "17")` | Cho biết từ phiên bản được tác giả ghi là `17`; chuỗi này không tự xác minh version |
| `@Deprecated(forRemoval = true)` | API được đánh dấu là **dự định loại bỏ** trong tương lai |
| `@Deprecated(since = "17", forRemoval = false)` | Deprecated từ mốc mô tả `17`, chưa đánh dấu dự định loại bỏ |

`forRemoval = true` **không** cam kết API sẽ biến mất vào một ngày cố định. Nếu ứng dụng đang dùng API này, hãy xem tài liệu và kế hoạch migration của nhà cung cấp; tránh tự suy ra thời hạn loại bỏ.

Để xem thông tin cảnh báo deprecated khi tự biên dịch dự án:

~~~bash
javac -Xlint:deprecation -encoding UTF-8 AnnotationBasicsDemo.java
~~~

Cảnh báo của `javac` thuộc luồng thông báo biên dịch, **không** phải stdout của chương trình chạy, và nội dung có thể tùy vị trí file/JDK. `@SuppressWarnings("deprecation")` có thể tắt cảnh báo tương ứng trong phạm vi được gắn, nhưng nên dành cho trường hợp có lý do rõ ràng thay vì dùng để che việc đang phụ thuộc API cũ. `forRemoval=true` có thể tạo cảnh báo thuộc nhóm `removal` riêng.

## 7. Ví dụ Java 17+ tự chứa, chạy được

Tạo file **AnnotationBasicsDemo.java**. Những khai báo trong một file sau đều biên dịch hợp lệ:

~~~java
public final class AnnotationBasicsDemo {
    private interface Audible {
        String sound();
    }

    private static class Animal {
        public String speak() {
            return "generic";
        }

        public String kind() {
            return "ANIMAL";
        }
    }

    private static final class Dog extends Animal {
        private final String name;

        Dog(String name) {
            this.name = name;
        }

        @Override
        public String speak() {
            return "woof";
        }

        @Override
        public String kind() {
            return "DOG";
        }

        @Override
        public String toString() {
            return "Dog(" + name + ")";
        }

        // Cùng tên nhưng tham số khác: overload, không phải override.
        public String speak(int times) {
            return "woof x" + times;
        }
    }

    private static final class Bird implements Audible {
        @Override
        public String sound() {
            return "chirp";
        }
    }

    private static final class LegacyApi {
        /**
         * @deprecated Use modernLabel(String) instead.
         */
        @Deprecated(since = "17", forRemoval = false)
        public String oldLabel(String value) {
            return "old:" + value;
        }

        public String modernLabel(String value) {
            return "new:" + value;
        }
    }

    public static void main(String[] args)
            throws NoSuchMethodException {
        Animal base = new Animal();
        Animal pet = new Dog("Rex");
        Dog dog = new Dog("Rex");
        Audible bird = new Bird();
        LegacyApi labels = new LegacyApi();

        System.out.println("parent=" + base.speak());
        System.out.println("override=" + dog.speak());
        System.out.println("dynamic=" + pet.speak());
        System.out.println("kind=" + pet.kind());
        System.out.println("interface=" + bird.sound());
        System.out.println("toString=" + dog.toString());
        System.out.println("overload=" + dog.speak(2));

        System.out.println("modern=" + labels.modernLabel("Java"));
        System.out.println("legacy=" + labels.oldLabel("Java"));

        // Minh họa annotation Deprecated có thể đọc bằng reflection.
        Deprecated info = LegacyApi.class
                .getDeclaredMethod("oldLabel", String.class)
                .getAnnotation(Deprecated.class);
        System.out.println("hasDeprecated=" + (info != null));
        System.out.println("since=" + info.since());
        System.out.println("forRemoval=" + info.forRemoval());
    }
}
~~~

Biên dịch/chạy trong thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 AnnotationBasicsDemo.java
java AnnotationBasicsDemo
~~~

**Expected stdout chính xác khi chạy `java AnnotationBasicsDemo`:**

~~~text
parent=generic
override=woof
dynamic=woof
kind=DOG
interface=chirp
toString=Dog(Rex)
overload=woof x2
modern=new:Java
legacy=old:Java
hasDeprecated=true
since=17
forRemoval=false
~~~

Giải thích: `dynamic=woof` và `kind=DOG` là ghi đè động qua biến kiểu `Animal`; `interface=chirp` minh họa triển khai interface; `overload=woof x2` gọi hàm khác danh sách tham số, không phải một override. `legacy` vẫn hoạt động mặc dù API cũ bị đánh dấu deprecated.

Ba dòng cuối dùng **reflection** của JDK để đọc `@Deprecated`; đây là phần quan sát bổ sung, không bắt buộc để hiểu API. `@Override` chủ yếu hỗ trợ kiểm tra lúc biên dịch và không dùng theo cách quan sát reflection này.

## 8. Lỗi thường gặp, checklist và bài tập

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| Phải viết `@Override` thì đa hình mới hoạt động | Không: annotation giúp kiểm tra ý định ghi đè |
| `@Override` được đặt trên mọi overload | Sai: overload khác danh sách tham số không phải override |
| Ghi đè static method như instance method | Sai: static method có thể bị che khuất, không override |
| Có thể `@Override` trên constructor | Không: constructor không phải phương thức ghi đè |
| `@Deprecated` khiến code không chạy | Không: vẫn chạy nếu API còn và lời gọi hợp lệ |
| `@Deprecated` tự cung cấp API thay thế | Không: cần đọc Javadoc/changelog để migration |
| Javadoc `@deprecated` và annotation `@Deprecated` là một | Khác nhau: tài liệu giải thích vs tín hiệu compiler/tool |
| `forRemoval=true` nghĩa là đã bị xóa | Chỉ là ý định loại bỏ; chưa phải xóa tức thời |
| Tắt mọi cảnh báo deprecated để code “sạch” | Nên xác định API thay thế và lộ trình migration |

**Bài 1.** Tạo lớp `Vehicle` có `move()`, lớp `Bike` ghi đè với `@Override`; gọi qua biến `Vehicle` để thấy dispatch theo đối tượng thực.

**Bài 2.** Cố ý viết sai `move` thành `mvoe` và giữ `@Override`. Ghi lại lỗi biên dịch; sửa tên để thành override hợp lệ.

**Bài 3.** Tạo interface `Greeting` có `hello()`, lớp triển khai ghi `@Override`. Vì sao phương thức triển khai phải có quyền truy cập phù hợp?

**Bài 4.** Đánh dấu phương thức `oldSum(int,int)` bằng `@Deprecated(since = "17", forRemoval = false)`, viết `sum(int,int)` thay thế và thêm Javadoc hướng dẫn chuyển đổi.

**Bài 5.** Thử `javac -Xlint:deprecation`, xác định nguồn cảnh báo. Giải thích tại sao dù có cảnh báo, `java` vẫn có thể gọi phương thức cũ.

### Ghi nhớ

**`@Override` cho biết “tôi định ghi đè một phương thức hợp lệ” và nhờ compiler bắt sai chữ ký. `@Deprecated` cho biết “API này không còn được khuyến nghị” nhưng không tự xóa hay ngăn runtime gọi nó.** Dùng Javadoc `@deprecated` để hướng dẫn thay thế; phân biệt overriding, overloading và static hiding; xử lý cảnh báo bằng hiểu rõ API thay vì chỉ che chúng.
