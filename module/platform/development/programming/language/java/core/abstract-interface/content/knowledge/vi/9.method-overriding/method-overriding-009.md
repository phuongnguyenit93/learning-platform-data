# Tham số varargs, mảng và các nhầm lẫn khi ghi đè phương thức trong Java

Trong khai báo phương thức, **T...** là cú pháp thuận tiện cho tham số mảng **T[]**. Vì vậy, thay varargs bằng mảng hoặc ngược lại không tự tạo chữ ký mới: hai khai báo có thể override lẫn nhau nếu các điều kiện khác đều hợp lệ.

## 1. Cùng kiểu tham số, khác cú pháp gọi

~~~java
class ParentVarargs {
    void print(String... words) {
        System.out.println(java.util.Arrays.toString(words));
    }
}

class ChildArray extends ParentVarargs {
    @Override
    void print(String[] words) {
        System.out.println("child: " + java.util.Arrays.toString(words));
    }
}
~~~

Với ParentVarargs parent = new ChildArray(), lời gọi parent.print("A", "B") hợp lệ vì khai báo được nhìn thấy lúc biên dịch là varargs. Compiler đóng hai chuỗi thành String[], rồi runtime dispatch tới ChildArray.print(String[]).

Ngược lại, với ChildArray child = new ChildArray(), lời gọi child.print("A", "B") không hợp lệ: khai báo được nhìn thấy qua kiểu ChildArray dùng String[], nên phải gọi child.print(new String[]{"A", "B"}).

Chiều ngược lại cũng đúng: lớp cha khai báo print(String[]), lớp con override bằng print(String...) vẫn có cùng kiểu tham số; tuy nhiên, gọi qua biến kiểu cha vẫn cần truyền mảng nếu khai báo ở cha không phải varargs.

## 2. Chương trình minh họa

~~~java
public class VarargsOverrideDemo {
    public static void main(String[] args) {
        ParentVarargs ref = new ChildArray();
        ref.print("Java", "17");
        ref.print(new String[]{"A", "B"});

        ChildArray direct = new ChildArray();
        direct.print(new String[]{"C"});
        ref.print((String) null);
        direct.print((String[]) null);
    }
}
~~~

Ghép với hai lớp ở mục 1, kết quả là:

~~~text
child: [Java, 17]
child: [A, B]
child: [C]
child: [null]
child: null
~~~

(String) null là một đối số null được đóng gói thành mảng một phần tử. (String[]) null truyền chính tham chiếu mảng null. Không nên dựa vào print(null) để biểu đạt ý định vì compiler có thể hiểu là mảng null và đưa ra cảnh báo; cast rõ kiểu sẽ dễ đọc hơn.

## 3. Ràng buộc chữ ký

- Varargs phải là tham số cuối cùng và mỗi phương thức chỉ có tối đa một tham số varargs.
- int... tương đương int[]; String[]... tương đương String[][].
- Không thể khai báo hai overload cùng lớp chỉ khác f(String...) và f(String[]); đó là hai chữ ký trùng nhau.
- Object[] và String[] là các kiểu tham số khác nhau, dù mảng String[] có thể gán cho Object[].
- Autoboxing ở lời gọi không biến int[] thành Integer[] và không tạo quan hệ override giữa hai chữ ký khác kiểu.

## 4. Reflection và generic varargs

Method.isVarArgs() cho biết **phương thức được khai báo** với cú pháp varargs hay không. Compiler có thể cho Parent.print(String...) và Child.print(String[]) override nhau dù isVarArgs() trả về khác nhau. Khi dùng reflection, tra cứu tham số bằng String[].class.

Varargs generic như List&lt;String&gt;... có thể gây cảnh báo do kiểu mảng không reifiable và nguy cơ heap pollution. @SafeVarargs chỉ được dùng ở các vị trí được Java cho phép; nó không phải cách bỏ qua cảnh báo tùy tiện.

**Ghi nhớ:** compile time quyết định cú pháp varargs có hợp lệ tại call site không; runtime dispatch mới chọn thân override. Khi debug, hãy kiểm tra cả kiểu tĩnh của receiver lẫn dạng khai báo varargs/mảng.