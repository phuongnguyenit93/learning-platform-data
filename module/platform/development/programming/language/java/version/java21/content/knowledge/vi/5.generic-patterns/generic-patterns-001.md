# Record generic và kiểu của các component trong pattern

Java 21 cho phép kết hợp generic record với record pattern để kiểm tra kiểu và lấy trực tiếp các component của một record. Trình biên dịch có thể suy luận type argument của record pattern từ kiểu tĩnh của giá trị được so khớp; nhờ đó biến pattern nhận đúng kiểu component sau khi các type parameter đã được thay thế. Cách viết này hữu ích khi xử lý dữ liệu có cấu trúc như kết quả API, sự kiện, thông tin phân trang hoặc các cặp giá trị.

Trong module Java 21, nội dung này tập trung vào generic record, kiểu của component, record pattern tường minh và suy luận kiểu, pattern lồng nhau, cùng các quy tắc an toàn khi làm việc với type erasure. Record patterns và pattern matching for switch đã là tính năng chính thức của Java 21, không cần bật preview.

## 1. Khai báo generic record

Record là một dạng khai báo lớp dữ liệu. Khi record có type parameter, các component có thể sử dụng những type parameter đó giống như thuộc tính và tham số của một lớp generic thông thường.

~~~java
record Box<T>(T value) {
}

record Pair<K, V>(K key, V value) {
}

record Page<T>(java.util.List<T> items, int pageNumber) {
}

class GenericRecordUsage {
    public static void main(String[] args) {
        Box<String> title = new Box<>("Java 21");
        Box<Integer> quantity = new Box<>(21);

        String text = title.value();
        Integer count = quantity.value();
    }
}
~~~

Với khai báo **Box<T>(T value)**, component **value** có kiểu T. Khi sử dụng **Box<String>**, kiểu component tương ứng là String; khi sử dụng **Box<Integer>**, kiểu component tương ứng là Integer. Các accessor do record cung cấp cũng trả về kiểu đã được tham số hóa tương ứng.

Toán tử diamond cho phép trình biên dịch suy luận type argument khi tạo đối tượng từ kiểu đích và các đối số constructor. Đây là suy luận kiểu khi khởi tạo record; cần phân biệt với suy luận type argument của record pattern ở các phần sau.

### Component có thể mang nhiều dạng kiểu

Component của generic record không bắt buộc phải có kiểu là một type parameter đơn lẻ. Nó có thể là kiểu generic lồng nhau, kiểu mảng, kiểu nguyên thủy hoặc một record khác.

~~~java
record ApiResult<T>(
        T data,
        java.util.List<T> warnings,
        int statusCode
) {
}

record TreeNode<T>(
        T value,
        java.util.List<TreeNode<T>> children
) {
}
~~~

Khi kiểu cụ thể là **ApiResult<String>**, các component lần lượt có kiểu String, List<String> và int. Với **TreeNode<Long>**, component **value** có kiểu Long và **children** có kiểu List<TreeNode<Long>>. Type argument được thay thế xuyên suốt cấu trúc component theo khai báo generic.

## 2. Record pattern lấy component như thế nào?

Record pattern kiểm tra một giá trị có thuộc record class được nêu trong pattern hay không. Nếu khớp, pattern gọi accessor tương ứng và tiếp tục so khớp các giá trị component theo thứ tự khai báo trong record.

~~~java
record Point(double x, double y) {
}

class PointExample {
    static double distanceFromOrigin(Object value) {
        if (value instanceof Point(double x, double y)) {
            return Math.sqrt(x * x + y * y);
        }
        return -1;
    }
}
~~~

Pattern **Point(double x, double y)** kiểm tra record Point và lấy hai component qua các accessor **x()** và **y()**. Hai biến pattern có kiểu double vì đó là kiểu component trong khai báo record. Việc tách component được thực hiện ngay trong điều kiện, không cần tạo biến trung gian rồi gọi accessor thủ công.

Record pattern có thể dùng trong biểu thức **instanceof**, câu lệnh **switch** và biểu thức **switch**. Các pattern lồng nhau cho phép đi sâu vào record component mà không cần viết chuỗi lời gọi accessor dài.

## 3. Viết tường minh type argument của generic record pattern

Với generic record, pattern có thể ghi rõ type argument. Ví dụ sau dùng kiểu Box<String> ở cả tham số và record pattern:

~~~java
record Box<T>(T value) {
}

class ExplicitGenericPattern {
    static String printBoxContents(Box<String> box) {
        if (box instanceof Box<String>(String value)) {
            return "Box chứa: " + value;
        }
        return "Không có Box";
    }
}
~~~

Trong pattern **Box<String>(String value)**:

- **Box<String>** xác định record type cùng type argument.
- Component **value** được thay thế từ T thành String.
- Biến pattern **value** có kiểu String và có thể gọi trực tiếp các phương thức của String.

Kiểu component trong danh sách pattern phải phù hợp với kiểu component sau khi áp dụng type argument. Với record có nhiều component, mỗi vị trí trong pattern tương ứng với một component theo đúng thứ tự khai báo.

~~~java
record Pair<K, V>(K key, V value) {
}

class PairPatternExample {
    static String describe(Pair<String, Integer> pair) {
        if (pair instanceof Pair<String, Integer>(
                String key,
                Integer value
        )) {
            return key + " = " + value;
        }
        return "Không có Pair";
    }
}
~~~

Trong ví dụ này, component đầu tiên có kiểu String và component thứ hai có kiểu Integer. Pattern có hai component; số lượng và thứ tự phải khớp với khai báo Pair.

## 4. Suy luận type argument và kiểu component bằng var

Java 21 có thể suy luận type argument của record pattern từ kiểu tĩnh của giá trị được so khớp. Vì vậy, thường không cần lặp lại type argument trong pattern.

~~~java
record Box<T>(T value) {
}

class InferredGenericPattern {
    static String printBoxContents(Box<String> box) {
        if (box instanceof Box(var value)) {
            return "Box chứa: " + value.toUpperCase();
        }
        return "Không có Box";
    }
}
~~~

Do biến **box** có kiểu tĩnh **Box<String>**, trình biên dịch suy luận pattern **Box(var value)** tương đương với **Box<String>(String value)**. Vì vậy **value** có kiểu String và có thể gọi **toUpperCase()**.

Từ khóa **var** trong component pattern yêu cầu trình biên dịch suy luận kiểu của biến pattern. Nó không có nghĩa là biến luôn mang kiểu Object. Kiểu được suy luận từ kiểu component sau khi áp dụng type argument của generic record.

Ví dụ với generic method:

~~~java
record Box<T>(T value) {
}

class GenericMethodPattern {
    static <T> T unwrap(Box<T> box) {
        if (box instanceof Box(var value)) {
            return value;
        }
        throw new IllegalArgumentException("box không được null");
    }
}
~~~

Trong phương thức trên, pattern được suy luận là **Box<T>(T value)**. Kiểu của biến pattern vẫn là T, nên phương thức trả về đúng kiểu T mà không cần ép kiểu thủ công.

### Suy luận với component generic phức tạp

Suy luận cũng áp dụng khi component là kiểu generic lồng nhau:

~~~java
record ApiResult<T>(
        T data,
        java.util.List<T> warnings
) {
}

class ApiResultPattern {
    static <T> int warningCount(ApiResult<T> result) {
        if (result instanceof ApiResult(var data, var warnings)) {
            return warnings.size();
        }
        return 0;
    }
}
~~~

Với tham số **ApiResult<T>**, trình biên dịch suy luận **data** có kiểu T và **warnings** có kiểu List<T>. Không cần viết lại các kiểu này trong pattern. Nếu kiểu component là một wildcard hoặc capture type, biến pattern giữ kiểu mà trình biên dịch suy luận được; không được tự giả định kiểu cụ thể hơn những gì khai báo cho phép.

## 5. Generic record pattern lồng nhau

Một component của record có thể là một generic record khác. Có thể đặt record pattern bên trong record pattern để lấy dữ liệu ở nhiều cấp.

~~~java
record Box<T>(T value) {
}

class NestedGenericPattern {
    static String unwrapNested(Box<Box<String>> box) {
        if (box instanceof Box(Box(var value))) {
            return value.toUpperCase();
        }
        return "Không có dữ liệu";
    }
}
~~~

Từ kiểu tĩnh **Box<Box<String>>**, trình biên dịch suy luận pattern bên ngoài là **Box<Box<String>>**, pattern bên trong là **Box<String>**, và biến **value** có kiểu String. Sự suy luận diễn ra đệ quy qua các generic record lồng nhau.

Ví dụ thực tế hơn kết hợp generic component với một record không generic:

~~~java
record Address(String city, String country) {
}

record Customer<T>(T id, Address address) {
}

class CustomerPatternExample {
    static String describe(Customer<String> customer) {
        if (customer instanceof Customer(
                var id,
                Address(var city, var country)
        )) {
            return id + " sống tại " + city + ", " + country;
        }
        return "Không có khách hàng hoặc địa chỉ";
    }
}
~~~

Trong pattern này, **id** được suy luận là String. Pattern Address lồng bên trong tách **city** và **country**, mỗi biến có kiểu String. Cách viết này phù hợp với các DTO có cấu trúc lồng nhau, miễn là từng cấp thực sự là record.

## 6. Dùng generic record pattern trong switch

Pattern matching for switch cũng là tính năng chính thức của Java 21. Khi selector có kiểu generic record cụ thể, trình biên dịch suy luận type argument của record pattern và kiểu của các component.

~~~java
record Box<T>(T value) {
}

class SwitchGenericPattern {
    static <T> String toDisplay(Box<T> box) {
        return switch (box) {
            case null -> "(null)";
            case Box(var value) -> String.valueOf(value);
        };
    }
}
~~~

Với selector có kiểu **Box<T>**, pattern **Box(var value)** được suy luận theo cùng T. Nhánh **case null** xử lý riêng selector null. Nếu không có nhánh null, một switch pattern không tự xem record pattern là cách khớp với giá trị null; khi selector là null, switch sẽ ném NullPointerException.

Pattern variable chỉ có hiệu lực trong vùng mà compiler xác định pattern đã khớp. Với **instanceof**, biến được dùng trong nhánh điều kiện đúng; với switch, biến được dùng trong phần thân của nhánh tương ứng. Không sử dụng biến pattern bên ngoài phạm vi đó.

## 7. Quy tắc null khi phân rã component

Record pattern bên ngoài không khớp với giá trị record null. Với pattern lồng nhau, nếu component tương ứng là null thì record pattern ở cấp trong cũng không khớp.

~~~java
record Address(String city) {
}

record Customer<T>(T id, Address address) {
}

class NullComponentPattern {
    static void inspect(Customer<String> customer) {
        if (customer instanceof Customer(var id, Address(var city))) {
            System.out.println(id + " - " + city);
        } else {
            System.out.println("Customer hoặc Address không khớp");
        }
    }
}
~~~

Nếu **customer** là null, pattern ngoài không khớp. Nếu customer có giá trị nhưng **address** là null, pattern Address lồng bên trong không khớp và toàn bộ điều kiện là false. Với component có kiểu tham chiếu, **var** được suy luận thành type pattern vô điều kiện cho kiểu component nên biến pattern có thể nhận giá trị null. Việc dùng **var** không tự thêm kiểm tra null cho component.

Khi dữ liệu đầu vào cho phép component null, hãy quyết định rõ muốn kiểm tra null hay muốn nhận giá trị null vào biến pattern. Không nên giả định mọi component được tách ra đều khác null.

## 8. Giới hạn an toàn với type erasure và raw type

Java triển khai generic bằng type erasure. Type argument như String trong Box<String> không trở thành một lớp runtime riêng. Trình biên dịch vẫn kiểm tra tính tương thích của kiểu tĩnh và giới hạn những record pattern nào được phép dùng, nhưng không thể kiểm tra nội dung generic đã bị xóa kiểu ở runtime như thể type argument được lưu đầy đủ.

Một generic record pattern với type argument cụ thể chỉ hợp lệ khi giá trị được so khớp có thể chuyển sang kiểu record đó mà không cần unchecked conversion. Ví dụ sau không biên dịch:

~~~java
record Box<T>(T value) {
}

class InvalidRawPattern {
    static void invalidPattern(Box rawBox) {
        if (rawBox instanceof Box<String>(var value)) {
            System.out.println(value);
        }
    }
}
~~~

**rawBox** dùng raw type Box. Chuyển từ raw Box sang Box<String> cần unchecked conversion, vì vậy compiler từ chối pattern này. Cách xử lý là giữ kiểu generic chính xác xuyên suốt API:

~~~java
record Box<T>(T value) {
}

class ValidGenericPattern {
    static void validPattern(Box<String> box) {
        if (box instanceof Box<String>(String value)) {
            System.out.println(value);
        }
    }
}
~~~

Tránh raw type, unchecked cast và việc làm mất type argument ở ranh giới API. Khi một phương thức nhận **Box<?>**, kiểu cụ thể bên trong chưa được biết; không được coi component là String nếu không có ràng buộc kiểu chứng minh điều đó.

Một record component có kiểu **List<T>** cũng không có nghĩa record pattern sẽ mở từng phần tử của List. Record pattern chỉ phân rã component của record. Sau khi lấy được List<T>, nếu cần xử lý phần tử thì dùng API của List hoặc một cơ chế duyệt phù hợp.

## 9. Chọn kiểu component và pattern phù hợp

| Tình huống | Cách viết | Kiểu component nhận được |
|---|---|---|
| Đã biết rõ kiểu generic | Box<String>(String value) | String |
| Kiểu tĩnh của giá trị đã xác định type argument | Box(var value) với Box<String> | String |
| Generic method đang giữ type parameter T | Box(var value) với Box<T> | T |
| Component là List<T> | Page(var items) với Page<T> | List<T> |
| Record generic lồng nhau | Box(Box(var value)) với Box<Box<String>> | String |
| Chỉ biết wildcard | Box(var value) với Box<?> | Kiểu capture chưa xác định cụ thể; không giả định là String |

Ưu tiên để compiler suy luận bằng **var** khi kiểu tĩnh của record đã rõ và tên biến thể hiện đủ ý nghĩa. Dùng kiểu tường minh trong component pattern khi muốn làm rõ hợp đồng dữ liệu hoặc khi người đọc cần thấy ngay kiểu mong đợi.

## 10. Checklist khi sử dụng generic record pattern

- [ ] Khai báo type parameter của record phù hợp với dữ liệu component.
- [ ] Dùng kiểu tham số hóa như Box<String>, không làm mất thông tin bằng raw type.
- [ ] Bảo đảm số lượng và thứ tự component trong pattern khớp khai báo record.
- [ ] Hiểu rằng **var** suy luận kiểu component sau khi áp dụng type argument.
- [ ] Dùng record pattern lồng nhau chỉ khi component tương ứng thực sự là record.
- [ ] Xử lý rõ trường hợp record hoặc component có thể null.
- [ ] Không giả định pattern kiểm tra được type argument đã bị xóa ở runtime.
- [ ] Dùng record patterns và switch patterns ở dạng chính thức của Java 21, không bật preview.

## Tài liệu tham khảo

- [Java SE 21: Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Java SE 21: Record Classes](https://docs.oracle.com/en/java/javase/21/language/records.html)
- [Java SE 21: Java Language Changes](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html)
- [Java Language Specification, Java SE 21: Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Java Language Specification, Java SE 21: Record Pattern Type Inference](https://docs.oracle.com/javase/specs/jls/se21/html/jls-18.html#jls-18.5.5)
- [JEP 440: Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441: Pattern Matching for switch](https://openjdk.org/jeps/441)
