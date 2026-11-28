# Varargs, mảng tham số và lời gọi mơ hồ

Trong Java 27, một phương thức có thể nhận một số lượng đối số thay đổi bằng cú pháp varargs (dấu ba chấm **...**). Varargs giúp lời gọi phương thức gọn hơn khi cần truyền từ không đến nhiều giá trị cùng kiểu. Ở cấp độ khai báo, tham số varargs vẫn có kiểu mảng; khi gọi, trình biên dịch quyết định truyền một mảng có sẵn hay tạo mảng để gom các đối số rời.

Điểm dễ gây lỗi là varargs tham gia vào cơ chế overload resolution cùng với tham số mảng, boxing, unboxing và các phép chuyển đổi kiểu. Vì thế, một lời gọi như **print(null)** có thể truyền cả mảng null, truyền một phần tử null hoặc trở thành lời gọi mơ hồ tùy tập overload đang khai báo.

Bài viết tập trung vào quy tắc còn áp dụng trong Java SE 27: cách khai báo varargs, cách truyền mảng, ba pha chọn phương thức, các trường hợp null, generic varargs và cách thiết kế API tránh lời gọi mơ hồ.

## 1. Tham số mảng và varargs

### 1.1. Tham số mảng thông thường

Một phương thức có thể nhận một mảng như tham số cuối cùng hoặc tham số ở bất kỳ vị trí nào:

~~~java
static void printNames(String[] names) {
    for (String name : names) {
        System.out.println(name);
    }
}
~~~

Khi gọi phương thức này, đối số tương ứng phải tương thích với kiểu String[]:

~~~java
String[] names = {"An", "Bình", "Chi"};

printNames(names);
printNames(new String[] {"Dũng", "Hà"});
~~~

Không thể truyền nhiều đối số String rời rạc vào vị trí của một tham số String[]:

~~~java
// printNames("An", "Bình"); // lỗi biên dịch
~~~

Phương thức nhận mảng có thể xử lý số phần tử bất kỳ, nhưng người gọi phải tạo hoặc cung cấp mảng.

### 1.2. Varargs là tham số có số lượng đối số thay đổi

Varargs (variable arity parameter) dùng dấu ba chấm sau kiểu phần tử:

~~~java
static void printNames(String... names) {
    for (String name : names) {
        System.out.println(name);
    }
}
~~~

Cách khai báo này cho phép gọi bằng không, một hoặc nhiều đối số:

~~~java
printNames();
printNames("An");
printNames("An", "Bình", "Chi");
~~~

Trình biên dịch tạo mảng phù hợp để truyền vào phương thức khi lời gọi sử dụng dạng varargs. Trong thân phương thức, names vẫn là một mảng String[], vì vậy có thể dùng length, truy cập phần tử, duyệt bằng vòng lặp hoặc truyền tiếp cho phương thức nhận mảng.

### 1.3. Các quy tắc khai báo

Một phương thức chỉ được có tối đa một tham số varargs và tham số đó phải nằm cuối danh sách tham số.

~~~java
static void log(String level, String... messages) {
    for (String message : messages) {
        System.out.println(level + ": " + message);
    }
}
~~~

Lời gọi:

~~~java
log("INFO");
log("INFO", "Application started");
log("WARN", "Retrying", "Connection is slow");
~~~

Các khai báo sau không hợp lệ:

~~~java
// Sai: tham số varargs không nằm cuối danh sách
// static void invalid(String... names, int limit) { }

// Sai: một phương thức không được có hai tham số varargs
// static void invalid(String... names, int... codes) { }
~~~

Nếu cần nhiều nhóm dữ liệu có số lượng thay đổi, hãy gom từng nhóm vào một mảng, collection hoặc kiểu dữ liệu riêng rồi truyền chúng như các tham số thông thường.

## 2. Kiểu thực sự của tham số varargs

### 2.1. Trong thân phương thức, varargs là một mảng

Với khai báo:

~~~java
static void calculateTotal(int... values) {
    int total = 0;

    for (int value : values) {
        total += value;
    }

    System.out.println(total);
}
~~~

Kiểu khai báo của tham số values là int[]. Vì vậy, có thể sử dụng các thao tác mảng:

~~~java
static void inspect(String... names) {
    System.out.println(names.length);

    if (names.length > 0) {
        System.out.println(names[0]);
    }
}
~~~

Khai báo String... không tạo ra một kiểu dữ liệu mới. Dấu ba chấm chỉ đánh dấu tham số cuối cùng của phương thức là tham số có số lượng đối số thay đổi.

### 2.2. Không thể overload chỉ bằng cách đổi mảng thành varargs

Hai khai báo sau có cùng tên và cùng kiểu tham số trong chữ ký phương thức:

~~~java
class InvalidOverload {
    void send(String[] values) {
    }

    // Lỗi biên dịch: cùng chữ ký với send(String[])
    // void send(String... values) {
    // }
}
~~~

Vì kiểu khai báo của tham số varargs là kiểu mảng, send(String[]) và send(String...) không phải hai overload khác nhau.

Điều này cũng quan trọng khi đọc API: nếu tài liệu ghi String..., phương thức vẫn thao tác trên mảng String[] ở bên trong.

### 2.3. Varargs với kiểu nguyên thủy và mảng nhiều chiều

Varargs có thể dùng với kiểu nguyên thủy:

~~~java
static int sum(int... numbers) {
    int result = 0;

    for (int number : numbers) {
        result += number;
    }

    return result;
}

int total = sum(10, 20, 30);
int[] values = {4, 5, 6};
int anotherTotal = sum(values);
~~~

Ở đây int... tương ứng với int[]. Mảng Integer[] không thể truyền trực tiếp vào tham số int... vì Integer[] không phải int[]. Các đối số Integer rời rạc có thể được unbox khi phù hợp với quy tắc chuyển đổi của lời gọi, nhưng mảng wrapper và mảng primitive vẫn là hai kiểu khác nhau.

Varargs cũng có thể nhận từng mảng làm phần tử:

~~~java
static void printGroups(String[]... groups) {
    for (String[] group : groups) {
        System.out.println(group.length);
    }
}

printGroups(
    new String[] {"A", "B"},
    new String[] {"C"},
    new String[] {"D", "E", "F"}
);
~~~

Kiểu của tham số groups trong thân phương thức là String[][].

## 3. Truyền đối số vào phương thức varargs

### 3.1. Truyền các giá trị rời

Khi truyền các giá trị rời, trình biên dịch gom các giá trị vào một mảng có kiểu phần tử tương ứng:

~~~java
static void show(String... values) {
    System.out.println("Số phần tử: " + values.length);
}

show("Java", "Kotlin", "Go");
~~~

Với lời gọi trên, phương thức nhận một mảng có ba phần tử. Các biểu thức đối số được đánh giá theo thứ tự từ trái sang phải trước khi chuyển quyền điều khiển vào thân phương thức.

### 3.2. Truyền mảng đã có

Có thể truyền một mảng tương thích trực tiếp:

~~~java
String[] frameworks = {"Spring", "Quarkus"};

show(frameworks);
~~~

Trong trường hợp này, lời gọi có thể được áp dụng như lời gọi fixed-arity với tham số kiểu mảng. Trình biên dịch truyền tham chiếu đến mảng đã có, không tạo một mảng lồng chứa mảng đó.

Nếu phương thức sửa phần tử:

~~~java
static void replaceFirst(String... values) {
    if (values.length > 0) {
        values[0] = "Updated";
    }
}

String[] names = {"Original", "Second"};
replaceFirst(names);

System.out.println(names[0]); // Updated
~~~

Mảng ban đầu của bên gọi cũng thay đổi vì tham số và biến bên gọi cùng tham chiếu đến một đối tượng mảng.

Tuy nhiên, nếu gán lại biến tham số:

~~~java
static void replaceArray(String... values) {
    values = new String[] {"New array"};
}

String[] names = {"Original"};
replaceArray(names);

System.out.println(names[0]); // Original
~~~

Việc gán lại values chỉ thay đổi biến tham số cục bộ. Java truyền giá trị tham chiếu theo cơ chế pass-by-value; phương thức nhận một bản sao của tham chiếu, không nhận quyền thay thế biến tham chiếu của bên gọi.

### 3.3. Không đối số, mảng rỗng và mảng null

Ba trường hợp sau có ý nghĩa khác nhau:

| Lời gọi | Ý nghĩa trong phương thức |
|---|---|
| **show()** | Nhận một mảng rỗng, có length bằng 0 |
| **show(new String[0])** | Nhận mảng rỗng do bên gọi tạo |
| **show((String[]) null)** | Nhận tham chiếu mảng null |

Nếu phương thức có thể được gọi với mảng null, hãy kiểm tra trước khi truy cập:

~~~java
static void safeShow(String... values) {
    if (values == null) {
        System.out.println("Mảng null");
        return;
    }

    System.out.println(values.length);
}
~~~

Không nên coi mảng rỗng và mảng null là tương đương. Mảng rỗng là một đối tượng mảng hợp lệ không chứa phần tử; null không tham chiếu đến đối tượng mảng nào.

### 3.4. Mảng được truyền như một đối số hay như một phần tử?

Với phương thức nhận Object..., mảng kiểu tham chiếu có thể tương thích trực tiếp với Object[] do tính hiệp biến của mảng. Vì vậy, khi truyền một String[], mảng đó có thể được dùng trực tiếp làm mảng varargs:

~~~java
static void inspectObjects(Object... values) {
    System.out.println(values.length);
}

String[] names = {"An", "Bình"};

inspectObjects(names);          // truyền mảng String[] như mảng tham số
inspectObjects((Object) names); // gom mảng names thành một phần tử Object
~~~

Ở lời gọi thứ nhất, tham số values tham chiếu đến mảng names. Ở lời gọi thứ hai, cast sang Object làm cho đối số không còn tương thích trực tiếp với kiểu mảng Object[]; trình biên dịch tạo một mảng Object[] có một phần tử, phần tử đó tham chiếu đến mảng names.

Đây là một nguồn nhầm lẫn phổ biến khi API sử dụng Object.... Nếu mục tiêu là truyền một mảng như một giá trị duy nhất, hãy thể hiện rõ ý định bằng cách cast sang Object hoặc tạo mảng bao ngoài phù hợp.

## 4. Lời gọi null với varargs

### 4.1. null có thể được hiểu là mảng null

Xét phương thức chỉ có một overload:

~~~java
static void print(String... values) {
    if (values == null) {
        System.out.println("null array");
    } else {
        System.out.println(values.length);
    }
}
~~~

Lời gọi:

~~~java
print(null);
~~~

null có thể chuyển đổi sang kiểu mảng String[]. Vì vậy, lời gọi này được xem là lời gọi fixed-arity truyền mảng null. Compiler thường phát cảnh báo vì đối số null có thể bị hiểu nhầm là một phần tử varargs.

Để thể hiện ý định rõ ràng, dùng một trong hai cách:

~~~java
print((String[]) null); // truyền mảng null
print((String) null);   // truyền một phần tử String có giá trị null
~~~

Lời gọi print((String) null) không thể khớp với tham số mảng String[] ở dạng fixed-arity, nên được xử lý như lời gọi variable-arity với một phần tử null.

Nếu muốn truyền không phần tử, gọi print(). Nếu muốn truyền một phần tử null, dùng print((String) null).

### 4.2. Vì sao null có thể làm overload trở nên mơ hồ?

Giả sử có hai overload:

~~~java
static void select(String... values) {
    System.out.println("String varargs");
}

static void select(Integer... values) {
    System.out.println("Integer varargs");
}
~~~

Khi gọi:

~~~java
// select(null); // lỗi biên dịch: lời gọi mơ hồ
~~~

Trong giai đoạn kiểm tra fixed-arity, hai tham số cuối lần lượt có kiểu String[] và Integer[]. null có thể chuyển đổi sang cả hai kiểu mảng. Tuy nhiên, String[] không phải subtype của Integer[] và ngược lại. Không có phương thức nào cụ thể hơn để trình biên dịch chọn, nên lời gọi bị mơ hồ.

Có thể giải quyết bằng cast theo kiểu mong muốn:

~~~java
select((String[]) null);
select((Integer[]) null);
select((String) null);
~~~

Hai lời gọi đầu truyền mảng null vào overload tương ứng. Lời gọi thứ ba truyền một phần tử String null vào overload String varargs.

### 4.3. Khi một overload cụ thể hơn

Không phải mọi lời gọi null đều mơ hồ. Xét:

~~~java
static void display(Object value) {
    System.out.println("Object");
}

static void display(String... values) {
    System.out.println("String array");
}
~~~

Lời gọi:

~~~java
display(null);
~~~

Ở dạng fixed-arity, phương thức varargs có kiểu tham số thực tế là String[]. Vì String[] là subtype của Object, tham số mảng cụ thể hơn tham số Object. Do đó, overload display(String...) được chọn và nhận mảng null.

Ví dụ này cho thấy cần xem varargs như một tham số mảng khi phân tích overload. Không thể kết luận rằng trình biên dịch sẽ luôn chọn phương thức varargs ở pha variable-arity.

## 5. Trình biên dịch chọn overload như thế nào?

Java không chọn phương thức chỉ dựa trên số lượng đối số. Trình biên dịch xác định tập phương thức có thể áp dụng, kiểm tra theo từng pha và cuối cùng chọn phương thức cụ thể nhất trong pha đầu tiên có phương thức phù hợp.

### 5.1. Ba pha overload resolution

| Pha | Quy tắc | Nội dung chính |
|---|---|---|
| 1. Strict invocation | Fixed-arity | Không dùng boxing, unboxing hoặc lời gọi variable-arity; cho phép các chuyển đổi strict như widening phù hợp |
| 2. Loose invocation | Fixed-arity | Cho phép thêm boxing và unboxing; vẫn chưa mở rộng varargs |
| 3. Variable-arity invocation | Variable-arity | Mới xem xét việc gom nhiều đối số vào tham số varargs cuối cùng |

Nếu đã tìm được phương thức phù hợp trong pha 1, trình biên dịch chọn phương thức cụ thể nhất trong pha đó và không tiếp tục sang pha 2 hoặc pha 3. Tương tự, nếu pha 2 có kết quả phù hợp thì không cần pha 3.

Điều này bảo đảm lời gọi có thể khớp với một phương thức fixed-arity sẽ không bị chuyển sang dạng varargs chỉ vì varargs cũng có thể nhận số đối số đó.

### 5.2. Ví dụ fixed-arity được ưu tiên

~~~java
static void process(Object value) {
    System.out.println("Object");
}

static void process(String... values) {
    System.out.println("String[]");
}

String[] names = {"An", "Bình"};

process(names); // String[]: khớp tham số mảng ở pha fixed-arity
process("An");  // String[]: được xét ở pha variable-arity
~~~

Với process(names), String[] khớp chính xác với tham số mảng của phương thức varargs trong pha fixed-arity. Không cần tạo mảng mới hoặc đi đến pha variable-arity.

Với process("An"), đối số kiểu String không thể truyền vào tham số String[] ở dạng fixed-arity. Trình biên dịch chuyển đến pha variable-arity và gom chuỗi vào mảng.

### 5.3. Boxing và unboxing có thể thay đổi overload được chọn

Xét:

~~~java
static void convert(long value) {
    System.out.println("long");
}

static void convert(Integer value) {
    System.out.println("Integer");
}

convert(10);
~~~

Đối số literal 10 có kiểu int. Chuyển từ int sang long là widening primitive conversion và có thể áp dụng trong pha strict invocation. Chuyển từ int sang Integer cần boxing, chỉ được xét trong pha loose invocation.

Vì pha strict đã tìm thấy convert(long) phù hợp, phương thức convert(Integer) không được xét để cạnh tranh ở pha sau. Kết quả là overload convert(long) được chọn.

Đây cũng là lý do không nên suy luận overload chỉ bằng cách đếm số bước chuyển đổi một cách trực giác; phải xét đúng thứ tự các pha theo JLS.

### 5.4. Chọn phương thức cụ thể nhất

Nếu có nhiều phương thức phù hợp trong cùng một pha, Java chọn phương thức cụ thể nhất (most specific). Quan hệ subtype của kiểu tham số thường là yếu tố quan trọng.

~~~java
static void printValue(Object value) {
    System.out.println("Object");
}

static void printValue(String value) {
    System.out.println("String");
}

printValue("Java"); // String
printValue(null);   // String
~~~

String là subtype của Object, nên overload nhận String cụ thể hơn. Với null, cả hai kiểu tham chiếu đều nhận được giá trị này, nhưng String vẫn cụ thể hơn Object.

Ngược lại, nếu các kiểu tham số không có quan hệ subtype và cùng phù hợp với một lời gọi, trình biên dịch có thể không xác định được phương thức cụ thể nhất. Khi đó, lời gọi bị báo mơ hồ.

### 5.5. Kiểu trả về không được dùng để phân biệt overload

Hai phương thức không thể chỉ khác nhau ở kiểu trả về:

~~~java
class InvalidReturnOverload {
    // int find(String value) { return 1; }

    // Lỗi biên dịch nếu khai báo cùng lúc với find(String) ở trên:
    // String find(String value) { return value; }
}
~~~

Overload resolution dựa trên tên phương thức, kiểu tham số và quy tắc áp dụng; kiểu trả về không làm cho hai khai báo có cùng chữ ký trở thành hai overload hợp lệ. Nếu hai thao tác có ý nghĩa khác nhau, hãy dùng tên phương thức khác hoặc thiết kế tham số thể hiện rõ mục đích.

## 6. Generic varargs và heap pollution

### 6.1. Vì sao generic varargs cần chú ý?

Java dùng type erasure cho generic. Với tham số như T..., kiểu khai báo của tham số là T[], nhưng ở runtime không có đủ thông tin kiểu để tạo một mảng generic chính xác như new T[].

Một số kiểu phần tử không reifiable, chẳng hạn List<String>, vì thông tin tham số generic bị xóa ở runtime. Khi khai báo hoặc gọi phương thức varargs có kiểu phần tử không reifiable, compiler có thể phát cảnh báo unchecked.

~~~java
static void printLists(List<String>... lists) {
    for (List<String> list : lists) {
        System.out.println(list);
    }
}
~~~

Tham số lists có kiểu khai báo List<String>[], nhưng mảng runtime không thể xác minh tham số kiểu String cho từng phần tử. Đây là nguồn gốc của rủi ro heap pollution.

### 6.2. Heap pollution là gì?

Heap pollution xảy ra khi một biến có kiểu tham số hóa được tham chiếu đến một đối tượng không thỏa mãn kiểu tham số mà mã nguồn đang giả định. Với generic varargs, việc truy cập mảng thông qua một tham chiếu kiểu rộng hơn có thể đưa phần tử không đúng kiểu vào mảng.

Ví dụ dưới đây minh họa một thao tác không an toàn:

~~~java
static void unsafe(List<String>... lists) {
    Object[] values = lists;
    values[0] = List.of(123);

    String first = lists[0].get(0); // có thể ném ClassCastException
}
~~~

Mảng varargs có thể được nhìn qua kiểu rộng hơn Object[]. Do type erasure, thao tác lưu List<Integer> vào phần tử của mảng runtime có component type là List có thể vượt qua kiểm tra mảng. Nhưng khi đọc lại như List<String> và lấy phần tử String, cast được compiler chèn vào có thể thất bại.

Vì vậy, không nên ghi phần tử có kiểu không được bảo đảm vào mảng generic varargs, không trả mảng đó ra ngoài và không để tham chiếu không an toàn thoát khỏi phương thức.

### 6.3. Dùng @SafeVarargs đúng cách

@SafeVarargs cho phép tác giả phương thức khẳng định rằng việc sử dụng tham số varargs không gây heap pollution. Annotation này ngăn compiler phát unchecked warning liên quan đến tham số generic varargs ở khai báo và lời gọi tương ứng.

Ví dụ một phương thức chỉ đọc các danh sách và không ghi giá trị sai kiểu vào mảng:

~~~java
@SafeVarargs
static <T> void printAll(List<T>... groups) {
    for (List<T> group : groups) {
        System.out.println(group);
    }
}
~~~

Trong Java hiện hành, @SafeVarargs có thể áp dụng cho:

- Phương thức static.
- Phương thức instance final.
- Phương thức instance private.
- Constructor có tham số varargs.

Không thể gắn annotation này lên một phương thức instance có thể bị override, vì lớp con có thể thay đổi cách sử dụng tham số. Annotation là lời cam kết của người viết mã; compiler không chứng minh toàn bộ thân phương thức là an toàn. Không dùng @SafeVarargs chỉ để làm mất cảnh báo nếu phương thức vẫn sửa mảng theo cách không an toàn hoặc làm lộ tham chiếu đến mảng.

## 7. Thiết kế API dùng varargs và overload an toàn

### 7.1. Khi nào nên dùng varargs?

Varargs phù hợp khi:

- Số đối số có thể là 0, 1 hoặc nhiều giá trị.
- Các giá trị có cùng kiểu hoặc cùng kiểu phần tử.
- Một mảng là cách biểu diễn tự nhiên cho nhóm dữ liệu đó.
- Người gọi thường có sẵn các giá trị rời thay vì phải tạo collection.

Ví dụ như phương thức định dạng chuỗi, ghi log, tính tổng số, kiểm tra nhiều điều kiện hoặc tạo tập giá trị ban đầu.

Nếu phương thức cần thêm tùy chọn có cấu trúc, dữ liệu có thể thay đổi hoặc cần thao tác như thêm/xóa phần tử, một tham số collection thường diễn đạt ý định tốt hơn varargs.

### 7.2. Tránh overload gây mơ hồ

Một số nguyên tắc thực tế:

1. Không khai báo overload chỉ khác nhau giữa T[] và T....
2. Tránh các overload varargs có kiểu phần tử không liên quan như String... và Integer... nếu người gọi có thể truyền null hoặc không truyền đối số.
3. Khi null có ý nghĩa nghiệp vụ, yêu cầu cast tường minh hoặc dùng API có tên riêng để phân biệt mảng null với một phần tử null.
4. Ưu tiên một overload fixed-arity rõ ràng cho trường hợp đặc biệt nếu nó giúp lời gọi dễ đọc.
5. Không dựa vào kiểu trả về để tạo overload.
6. Với generic varargs, cân nhắc dùng List<T> hoặc một kiểu collection thay thế; chỉ dùng @SafeVarargs sau khi kiểm tra thân phương thức thực sự an toàn.

Ví dụ API có hai ý nghĩa riêng nên dùng tên riêng:

~~~java
static void printAll(String... values) {
    // Xử lý danh sách giá trị
}

static void printArrayReference(String[] values) {
    // Xử lý mảng, kể cả trường hợp null
}
~~~

Trong thực tế, nếu hai phương thức có cùng kiểu tham số thì không thể khai báo như hai overload cùng tên. Vì vậy, dùng hai tên khác nhau giúp thể hiện rõ sự khác biệt về ý nghĩa.

### 7.3. Checklist khi đọc một lời gọi varargs

Khi một lời gọi khó hiểu, hãy kiểm tra theo thứ tự:

1. Tham số cuối của phương thức có phải varargs không? Kiểu phần tử là gì?
2. Đối số cuối có phải mảng tương thích với kiểu tham số mảng không?
3. Nếu truyền null, nó có thể khớp với kiểu mảng ở pha fixed-arity không?
4. Có overload nào khác cùng phù hợp trong pha strict hoặc loose không?
5. Chỉ khi hai pha fixed-arity không tìm được phương thức mới xét pha variable-arity.
6. Nếu còn nhiều ứng viên, kiểu tham số nào cụ thể hơn theo quan hệ subtype?
7. Nếu không có phương thức cụ thể nhất, lời gọi có bị mơ hồ không?

Cách kiểm tra này đặc biệt hữu ích khi overload kết hợp mảng, varargs, boxing, unboxing và kiểu tham chiếu.

## 8. Ví dụ tổng hợp

~~~java
import java.util.List;

public class VarargsExamples {

    static void show(String... values) {
        if (values == null) {
            System.out.println("null array");
            return;
        }

        System.out.println("count = " + values.length);
        for (String value : values) {
            System.out.println(value);
        }
    }

    static int sum(int... numbers) {
        int total = 0;
        for (int number : numbers) {
            total += number;
        }
        return total;
    }

    static void select(String... values) {
        System.out.println("String varargs");
    }

    static void select(Integer... values) {
        System.out.println("Integer varargs");
    }

    @SafeVarargs
    static <T> void inspectGroups(List<T>... groups) {
        for (List<T> group : groups) {
            System.out.println(group);
        }
    }

    public static void main(String[] args) {
        show();
        show("Java", "JVM");

        String[] names = {"An", "Bình"};
        show(names);

        show((String) null);
        show((String[]) null);

        System.out.println(sum(1, 2, 3));
        System.out.println(sum(new int[] {4, 5, 6}));

        // select(null); // lỗi: String[] và Integer[] không có quan hệ subtype
        select((String[]) null);
        select((Integer[]) null);
        select((String) null);

        inspectGroups(
            List.of("A", "B"),
            List.of("C")
        );
    }
}
~~~

Ví dụ này gom các trường hợp quan trọng: lời gọi không đối số, truyền các phần tử rời, truyền mảng có sẵn, phân biệt null array với phần tử null, overload mơ hồ và generic varargs.

## 9. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| T... là một kiểu dữ liệu riêng | Trong khai báo, tham số varargs có kiểu mảng T[] |
| Có thể khai báo varargs ở bất kỳ vị trí nào | Varargs phải là tham số cuối và mỗi phương thức chỉ có tối đa một tham số varargs |
| method(T[]) và method(T...) là hai overload | Chúng có cùng kiểu tham số và cùng chữ ký |
| Truyền mảng vào varargs luôn tạo mảng lồng | Mảng tương thích có thể được truyền trực tiếp ở dạng fixed-arity |
| method() và method((T[]) null) giống nhau | Một lời gọi nhận mảng rỗng; lời gọi còn lại nhận tham chiếu mảng null |
| method(null) luôn có nghĩa là một phần tử null | Thông thường null có thể khớp với kiểu mảng; dùng cast (T) null để truyền một phần tử null |
| Compiler luôn ưu tiên varargs | Fixed-arity được xét trước; variable-arity là pha thứ ba |
| Overload chỉ cần có kiểu trả về khác nhau | Chữ ký phương thức không phân biệt bằng kiểu trả về |
| @SafeVarargs tự kiểm tra và sửa heap pollution | Annotation là cam kết của người viết; thân phương thức vẫn phải an toàn |
| Mảng varargs không thể bị thay đổi từ bên trong | Mảng có thể bị sửa phần tử; thay đổi đó có thể được bên gọi quan sát nếu cùng tham chiếu |

## 10. Tự kiểm tra kiến thức

1. Vì sao tham số String... values có thể dùng values.length trong thân phương thức?
2. Vì sao không thể khai báo đồng thời send(String[]) và send(String...) trong cùng một class?
3. Sự khác nhau giữa show(), show((String) null) và show((String[]) null) là gì?
4. Khi truyền một biến String[] vào phương thức show(String... values), trình biên dịch có cần tạo một mảng mới không?
5. Ba pha overload resolution của Java diễn ra theo thứ tự nào?
6. Vì sao select(null) mơ hồ khi có select(String...) và select(Integer...)?
7. Khi nào @SafeVarargs có thể được sử dụng trong Java hiện hành?
8. Heap pollution có thể xảy ra như thế nào với generic varargs?

## 11. Nguồn tham khảo chính thức

- [Java Language Specification, Java SE 27 — §8.4.1 Formal Parameters](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.4.1): khai báo tham số thường, tham số varargs và kiểu mảng của tham số varargs.
- [Java Language Specification, Java SE 27 — §8.4.2 Method Signature](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.4.2): chữ ký phương thức và quy tắc xác định hai khai báo có cùng chữ ký.
- [Java Language Specification, Java SE 27 — §9.6.4.7 @SafeVarargs](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-9.html#jls-9.6.4.7): phạm vi áp dụng và ý nghĩa của annotation SafeVarargs.
- [Java Language Specification, Java SE 27 — §15.12 Method Invocation Expressions](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-15.html#jls-15.12): chọn phương thức, overload resolution, ba pha áp dụng và đánh giá đối số.
- [Java Language Specification, Java SE 27 — §4.7 Reifiable Types](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-4.html#jls-4.7): kiểu reifiable và giới hạn liên quan đến generic.
- [Java Language Specification, Java SE 27 — §4.12.2 Variables of Reference Type](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-4.html#jls-4.12.2): heap pollution và các tình huống liên quan đến kiểu tham chiếu.
