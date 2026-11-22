# Đọc bytecode biểu thức, vòng lặp và phép gán để dự đoán thứ tự thực thi

## 1. Mục tiêu và cách nhìn đúng về bytecode

Để hiểu một chương trình Java thực hiện hành động nào trước, hành động nào sau, bạn cần kết hợp **quy tắc đánh giá biểu thức của ngôn ngữ Java** với **luồng điều khiển và operand stack của JVM**. Lệnh bytecode không tương ứng một-một với từng dòng mã nguồn: một biểu thức có thể thành nhiều lệnh nạp toán hạng, gọi phương thức, tính toán, sao chép, ghi biến và rẽ nhánh; một vòng lặp thường là tập hợp các nhãn/offset và lệnh nhảy.

Sau bài học, bạn sẽ:

- Biết đọc **javap -c**: offset, opcode, operand, constant-pool reference và điểm đích của lệnh nhảy.
- Theo dõi **local variable slots** và **operand stack** khi thực thi **iload**, **istore**, **iadd**, **imul**, **iinc** và **ireturn**.
- Dự đoán thứ tự của toán hạng, lời gọi phương thức, phép gán, **++i**, **i++**, **+=** và truy cập phần tử mảng.
- Phân tích **if/else**, **for**, **while**, **do-while**, **continue**, **break**, **&&**, **||** và toán tử ba ngôi bằng control-flow graph.
- Phân biệt một thứ tự hành vi **được Java bảo đảm** với một cách phát mã bytecode **do javac lựa chọn**.
- Tránh đọc nhầm thứ tự dòng trong disassembly thành thứ tự mọi dòng được thực thi; khi có nhánh/loop phải lần theo **program counter (PC)** thực tế.

Ví dụ dùng Java 17+; một số mã opcode được trình bày ở dạng **minh họa bytecode tiêu biểu**. Bạn cần chạy **javap** trên chính class file mình biên dịch để biết offset và lệnh chính xác.

## 2. Khung thực thi: frame, locals, operand stack và PC

Mỗi lần gọi phương thức Java, JVM tạo một frame chứa, trong số các thành phần khác, **bảng biến cục bộ (local variables)** và **operand stack**. PC chỉ tới instruction sẽ được thực thi kế tiếp trong luồng bytecode của phương thức đang chạy.

~~~text
            Java bytecode của phương thức
        offset 0 -> lệnh A
        offset 1 -> lệnh B
        offset 4 -> lệnh C       <---- PC có thể nhảy tới đây
        offset 7 -> lệnh D
        offset 8 -> lệnh E
                         |
                         v
Frame đang thực thi:
  Local variables:
    slot 0: tham số / this / biến
    slot 1: biến khác
    ...
  Operand stack:
    top -> giá trị vừa được đẩy
           các giá trị đang chờ được xử lý
  ...
~~~

Quy tắc thao tác cơ bản:

1. Lệnh **load** thường đọc một local slot và **đẩy** giá trị lên operand stack.
2. Lệnh tính toán thường **lấy** các toán hạng từ stack và **đẩy** kết quả trở lại.
3. Lệnh **store** thường **lấy** một giá trị khỏi stack và ghi vào local slot.
4. Lệnh nhánh có điều kiện lấy giá trị cần kiểm tra và quyết định PC đi tới đích nhảy hay instruction tiếp theo.
5. Lệnh gọi method chuẩn bị receiver và arguments theo quy ước JVM; method được gọi tạo frame riêng, sau đó có thể trả kết quả cho caller.
6. **return/ireturn/...** kết thúc frame hiện tại và quay về caller, trừ các trường hợp hoàn tất bất thường qua exception.

Ví dụ mô phỏng ngăn xếp khi thực hiện **(a + b) * 2**, với **a=3, b=4**:

| Instruction minh họa | Locals | Operand stack sau instruction (đáy → đỉnh) |
| --- | --- | --- |
| Trước khi chạy | a=3, b=4 | **[]** |
| **iload_0** | không đổi | **[3]** |
| **iload_1** | không đổi | **[3, 4]** |
| **iadd** | không đổi | **[7]** |
| **iconst_2** | không đổi | **[7, 2]** |
| **imul** | không đổi | **[14]** |
| **ireturn** | hoàn tất method | Trả **14** cho caller |

Bảng chỉ minh họa một phương thức **static** có hai tham số int ở slot 0 và 1. Trong instance method, slot 0 thường là **this**. Các instruction thật có thể khác do tối ưu hằng, cách bố trí locals hoặc khác compiler.

### 2.1. Những opcode hay gặp

| Nhóm | Opcode | Vai trò |
| --- | --- | --- |
| Nạp hằng | **iconst_0**, **iconst_1**, **bipush**, **sipush**, **ldc** | Đẩy hằng lên stack |
| Nạp local | **iload**, **iload_0**... | Đẩy int từ local slot |
| Ghi local | **istore**, **istore_0**... | Lấy int ở stack ghi vào slot |
| Tính toán | **iadd**, **isub**, **imul**, **idiv**, **irem** | Phép toán int, operand lấy từ stack |
| Tăng local | **iinc index, delta** | Cộng hằng delta trực tiếp vào một local int; không lấy/đẩy operand stack |
| Điều kiện một int | **ifeq**, **ifne**, **iflt**, **ifle**, **ifgt**, **ifge** | So sánh với số 0, rẽ nhánh |
| So sánh hai int | **if_icmpeq**, **if_icmpne**, **if_icmpge**... | Lấy hai int, kiểm tra quan hệ |
| Nhảy vô điều kiện | **goto**, **goto_w** | Đổi PC sang một offset |
| Trả về | **ireturn**, **areturn**, **return** | Kết thúc method |
| Sao chép/đổi vị trí | **dup**, **dup_x1**, **dup2**, **swap** | Tổ chức giá trị trên stack, hữu ích trong gán/++ |
| Mảng | **iaload**, **iastore**, **arraylength** | Đọc, ghi và lấy độ dài mảng |
| Field | **getfield**, **putfield**, **getstatic**, **putstatic** | Đọc/ghi trường instance/static |
| Gọi method | **invokestatic**, **invokevirtual**, **invokeinterface**, **invokespecial**, **invokedynamic** | Gọi hoặc liên kết thao tác động |

Chữ **i** chỉ kiểu tính toán **int** ở JVM; source **byte**, **short**, **char**, **boolean** đôi khi cũng được xử lý thông qua các opcode int. **long/double** dùng hai units trong mô hình frame và có opcode riêng.

## 3. Đọc đầu ra javap -c mà không nhầm offset

Cú pháp thông dụng:

~~~bash
javac --release 17 FileName.java
javap -c -p FileName
~~~

Ký hiệu mẫu:

~~~text
  0: iload_0
  1: iload_1
  2: iadd
  3: ireturn
~~~

- **0, 1, 2, 3** là **bytecode offsets**, không phải số dòng source.
- **iload_0** có thể là một instruction dài 1 byte; instruction có operand có thể dài hơn.
- Một lệnh như **6: if_icmpge 19** nghĩa là nếu điều kiện đúng, PC tới offset **19** trong cùng method; nếu sai, đi tiếp instruction kế tiếp. Số **19** trong javap được in là target **offset đích**, không phải giá trị boolean.
- **#n** sau các opcode như **invokevirtual #n**, **getfield #n** là chỉ số tham chiếu constant pool, không phải địa chỉ mã máy hay giá trị đang chạy.
- Phần chú giải sau **//** thường diễn giải constant pool reference, method descriptor hoặc type. Chúng giúp tìm đúng method/field được gọi.

Khi có vòng lặp, thứ tự các dòng xuất hiện trong javap là **thứ tự lưu lệnh**, không phải chuỗi hành động chỉ đi qua một lần. Phải đi theo PC và mọi branch target, kể cả **goto** nhảy ngược.

### 3.1. Gắn kết với source code

Dùng thêm:

~~~bash
javap -c -p -l FileName
javap -v -p FileName
~~~

- **-l** hiển thị thông tin line/local-variable tables **nếu có**; không phải class file nào cũng kèm đủ debug metadata.
- **-v** hiển thị constant pool, Code attributes, StackMapTable và những chi tiết khác để kiểm tra.
- **-p** cho phép xem cả thành viên private.

Không nên khẳng định mọi statement Java tạo một dải bytecode riêng hoặc số dòng source tăng cùng PC. Compiler có thể gộp hằng, tạo synthetic methods, tối ưu nhánh không cần thiết, thay cách lặp và thay đổi thứ tự lưu lệnh miễn bảo toàn ngữ nghĩa Java.

## 4. Đánh giá biểu thức từ trái sang phải: thứ tự khác độ ưu tiên

**Java Language Specification (JLS §15.7)** bảo đảm toán hạng của nhiều biểu thức được đánh giá **từ trái sang phải** theo quy tắc từng dạng biểu thức. Điều này cần phân biệt với **precedence** (độ ưu tiên toán tử) và **associativity** (cách nhóm biểu thức).

Ví dụ:

~~~java
// Minh họa bên trong một phương thức Java.
int result = left() + right() * 4;
~~~

**right() * 4** được nhóm với phép nhân vì phép nhân có độ ưu tiên cao hơn phép cộng, **nhưng left() vẫn được gọi trước right()** do left operand của phép cộng được đánh giá trước right operand.

Một thứ tự hành động hợp lệ:

~~~text
1. Gọi left() và lấy kết quả.
2. Gọi right() và lấy kết quả.
3. Nhân giá trị trả về của right() với 4.
4. Cộng kết quả của left() với tích vừa có.
5. Ghi tổng vào result.
~~~

Compiler có thể dùng operand stack để giữ kết quả **left()** trong khi tiếp tục tính vế phải.

**Không được kết luận:** “Nhân ưu tiên cao nên side effect trong right() phải xảy ra trước side effect trong left().” Ưu tiên quyết định **cấu trúc phép toán**, còn evaluation order quyết định **thời điểm đánh giá**.

### 4.1. Tham số method cũng đánh giá theo thứ tự

~~~java
// Ví dụ minh họa:
combine(first(), second(), third());
~~~

Trong Java, method receiver expression (nếu có) được xử lý theo quy tắc lời gọi, sau đó các argument expressions được đánh giá từ trái sang phải. Nếu **first()** ném exception thì **second()** và **third()** không tiếp tục được đánh giá; không phải compiler tùy ý đổi chúng để tối ưu.

Lúc đọc bytecode, hãy theo dõi các **invoke...** và vị trí kết quả được đẩy lên stack. Bước gọi **combine** thực sự diễn ra khi các argument cần thiết đã được đánh giá xong.

### 4.2. Ngoại lệ và side effect là bằng chứng của thứ tự

Ví dụ minh họa:

~~~java
// Minh họa, không phải chương trình độc lập:
int value = 10 / divisor() + logAndReturn(3);
~~~

Nếu **divisor()** trả **0**, instruction chia int ném **ArithmeticException** trước khi Java đánh giá toán hạng **logAndReturn(3)** phía sau phép cộng. Vì vậy side effect của **logAndReturn** không xảy ra.

Một trình tối ưu/JIT có thể thay cách triển khai nội bộ, nhưng kết quả có thể quan sát phải giữ quy tắc Java như các side effects/exceptions được yêu cầu. Không suy từ một đoạn disassembly thiếu side effects rằng Java không có thứ tự đánh giá.

## 5. Ví dụ runnable số 1: quan sát thứ tự bằng console

Tạo tệp **BytecodeOrderDemo.java**:

~~~java
public class BytecodeOrderDemo {
    static int next(String name, int value) {
        System.out.println("eval:" + name);
        return value;
    }

    static boolean left() {
        System.out.println("check:left");
        return false;
    }

    static boolean right() {
        System.out.println("check:right");
        return true;
    }

    public static void main(String[] args) {
        int expression = next("A", 2) + next("B", 3) * 4;
        System.out.println("expr=" + expression);

        int x = 4;
        int assigned = (x = 7) + x++;
        System.out.println("assign:result=" + assigned + ",x=" + x);

        int p = 2;
        int increments = ++p + p++;
        System.out.println("inc:both=" + increments + ",p=" + p);

        boolean shortCircuit = left() && right();
        System.out.println("and=" + shortCircuit);

        boolean eagerAnd = left() & right();
        System.out.println("eagerAnd=" + eagerAnd);

        int[] array = {10, 20};
        int index = 0;
        array[index++] += next("delta", 3);
        System.out.println("array:first=" + array[0] + ",index=" + index);

        int sum = 0;
        for (int i = 0; i < 4; i++) {
            if (i == 1) {
                continue;
            }
            if (i == 3) {
                break;
            }
            sum += i;
        }
        System.out.println("loop=" + sum);
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 BytecodeOrderDemo.java
java BytecodeOrderDemo
~~~

**Stdout chính xác:**

~~~text
eval:A
eval:B
expr=14
assign:result=14,x=8
inc:both=6,p=4
check:left
and=false
check:left
check:right
eagerAnd=false
eval:delta
array:first=13,index=1
loop=2
~~~

Vì sao thứ tự như vậy?

1. **next("A",2)** được gọi trước **next("B",3)** dù phép nhân ưu tiên hơn phép cộng. Tổng là **2 + 3 * 4 = 14**.
2. **(x = 7)** gán **x** thành 7 và biểu thức gán có giá trị 7. **x++** trả giá trị cũ 7 rồi tăng x thành 8; **assigned = 7 + 7 = 14**.
3. **++p** tăng p từ 2 lên 3 rồi trả 3; **p++** trả 3 rồi tăng p lên 4; biểu thức tổng là **6**.
4. **left() && right()** dừng khi left trả false nên **right() không chạy**.
5. **left() & right()** khi áp dụng cho boolean vẫn đánh giá **cả hai vế**, kết quả là false.
6. **array[index++] += next("delta",3)** lấy phần tử tại chỉ số cũ 0, ghi nhớ giá trị hiện tại là 10, đánh giá delta = 3 rồi ghi 13 vào **array[0]**; index trở thành 1.
7. Vòng for đi qua i=0 (cộng 0), i=1 (continue rồi cập nhật i), i=2 (cộng 2), i=3 (break). Kết quả **sum=2**.

Ví dụ cố ý dùng các biểu thức chứa side effect để nhìn rõ evaluation order. Trong code nghiệp vụ thực tế, tách side effect thành các dòng riêng thường giúp bảo trì và tránh nhầm hơn.

## 6. Phép gán đơn: lưu vào local, field hay array

Xét:

~~~java
// Ví dụ minh họa:
int a = 2;
int b = 5;
a = b + 3;
~~~

Một cách tổ chức bytecode tiêu biểu:

~~~text
... push 2; store a
... push 5; store b

load b
push 3
iadd
store a
~~~

Điểm quan trọng là **b + 3** được tính trước khi giá trị mới được ghi vào **a**. Phép gán trong Java là một **expression**: sau khi thực hiện, nó có giá trị dùng được bởi biểu thức bao ngoài.

Ví dụ **int z = (a = 7) + a;**: phép gán bên trái xảy ra trước khi đọc **a** bên phải, nên cả hai toán hạng đều bằng 7 (nếu không có tác động ngoài luồng đang xét), kết quả 14.

### 6.1. Local variable và operand stack là hai nơi khác nhau

Đừng nhầm **istore_1** là “đưa giá trị lên stack”: opcode này lấy giá trị đang ở stack rồi **lưu xuống** local slot 1. **iload_1** làm chiều ngược lại. Thứ tự toán hạng của **isub/idiv** đặc biệt quan trọng: stack **[a, b]** (b trên đỉnh) rồi **isub** cho **a - b**, không phải **b - a**.

Ví dụ stack:

~~~text
iconst_3     -> [3]
iconst_2     -> [3, 2]
isub         -> [1]
~~~

### 6.2. Gán có thể cần giữ giá trị kết quả

Nếu giá trị gán còn được dùng, ví dụ:

~~~java
// Minh họa:
int a;
int b;
b = (a = 5);
~~~

Compiler có thể dùng **dup** hoặc một cách tổ chức stack tương đương để vừa lưu vào **a** vừa giữ lại giá trị 5 cho phép gán **b**. Nếu gán là statement độc lập, không cần giữ giá trị sau khi store.

Chính vì vậy những lệnh **dup**, **dup_x1**, **dup_x2** thường xuất hiện cạnh phép gán field/array, biểu thức tăng và các thao tác vừa ghi vừa cần trả một giá trị. Không nên suy ngược rằng cứ có **dup** là source đã viết một phép gán cụ thể nào đó.

## 7. Prefix ++i, postfix i++ và iinc

Với biến local kiểu **int**:

~~~java
int i = 3;
int oldValue = i++; // oldValue = 3, i = 4
int newValue = ++i; // newValue = 5, i = 5
~~~

Khác biệt là **giá trị của biểu thức**, không chỉ khác thời điểm cập nhật:

| Biểu thức | Giá trị biến sau thao tác | Giá trị biểu thức |
| --- | ---: | ---: |
| **i++**, trước đó i=3 | 4 | 3 |
| **++i**, trước đó i=3 | 4 | 4 |
| **i--**, trước đó i=3 | 2 | 3 |
| **--i**, trước đó i=3 | 2 | 2 |

**iinc index, delta** là instruction JVM tăng một local int mà không cần đi qua operand stack. Nếu giá trị biểu thức **i++** cần được giữ, compiler có thể **iload** giá trị cũ trước **iinc**; nếu là **++i**, có thể **iinc** trước rồi **iload** giá trị mới.

Ví dụ bytecode **minh họa**, không bảo đảm mọi javac chọn đúng dãy:

~~~text
i++ khi cần lấy giá trị cũ:
    iload <slot>
    iinc <slot>, 1

++i khi cần lấy giá trị mới:
    iinc <slot>, 1
    iload <slot>
~~~

Nếu chỉ viết **i++;** làm statement, giá trị cũ không được dùng, compiler có thể chỉ sinh **iinc**. Với field, array component, kiểu **long**, hoặc các biểu thức có side effects phức tạp, không thể đơn giản áp dụng **iinc** cho mọi trường hợp; bytecode có thể cần **getfield/putfield**, **iaload/iastore**, **dup** và các opcode kiểu phù hợp.

### 7.1. ++ không đồng nhất với toán tử += ở mọi trường hợp

Ở Java source, **i++** có quy tắc trả giá trị cũ, **++i** trả giá trị mới; **i += 1** là compound assignment trả giá trị đã cập nhật. Với local **int** không có side effect khác, một compiler có thể dùng cùng **iinc** làm bước cập nhật, nhưng khi biểu thức cần có giá trị thì phải giữ đúng cách nạp trước/sau.

Ví dụ **int r = i++ + ++i;** với **i = 1**:

~~~text
vế trái i++  -> trả 1, i thành 2
vế phải ++i  -> i thành 3, trả 3
r = 1 + 3 = 4, i cuối = 3
~~~

Đây là Java hợp lệ và có thứ tự đánh giá xác định, dù cách viết phụ thuộc nhiều side effects rất dễ gây nhầm khi review code.

## 8. Phép gán kết hợp += và thứ tự đánh giá bên trái

Phép **x += expr** có tác dụng giống **x = (T) (x + expr)** đối với kiểu T của x, **ngoại trừ** biểu thức xác định biến ở vế trái chỉ được đánh giá **một lần** và giá trị cũ được đọc/ghi nhớ theo ngữ nghĩa compound assignment.

Ví dụ:

~~~java
// Minh họa trong một phương thức:
int x = 10;
x += 3; // x = 13
~~~

Với local **int** và hằng số phù hợp, javac có thể biên dịch kiểu **iinc**, thay vì bắt buộc **iload; iconst; iadd; istore**. Vì vậy nên so **hành vi** và stack/local effect, không ép mọi phép += thành bốn instruction cố định.

### 8.1. Trường hợp ++ bên chỉ số của mảng

~~~java
// Minh họa:
int[] values = {10, 20};
int k = 0;
values[k++] += 3;
~~~

Hành vi:

1. Xác định array reference **values** và index expression **k++** (giá trị index cũ = 0, sau đó k=1).
2. Kiểm tra truy cập phần tử thích hợp và lấy **values[0] = 10**.
3. Đánh giá RHS **3**; cộng thành 13.
4. Ghi lại **values[0] = 13**.

Kết quả **values[0] = 13** và **k = 1**. **index expression chỉ được đánh giá một lần**, không phải hai lần như khi viết một biểu thức thay thế cẩu thả:

~~~java
// KHÔNG tương đương, vì k++ bị chạy hai lần:
values[k++] = values[k++] + 3;
~~~

Mẫu bytecode của compound array assignment thường phải giữ reference, index và old value trên stack qua các lệnh như **dup2**, **iaload**, **iadd**, **iastore**. Dãy lệnh chính xác thay đổi theo kiểu mảng và compiler.

### 8.2. Tại sao += trên byte có thể dùng i2b?

~~~java
byte b = 127;
b += 1;        // Hợp lệ; b trở thành -128
// b = b + 1;  // Compile-time error: b + 1 có kiểu int
~~~

Ngôn ngữ Java cho phép compound assignment với bước thu hẹp về kiểu đích. JVM có thể tính toán qua int rồi dùng **i2b** để đưa kết quả về ngữ nghĩa byte. Không nên cho rằng mọi biến byte được cộng trực tiếp bằng một instruction “byte add”; opcode **iadd** vận hành theo int computational type.

## 9. Field và array assignment: nhận diện thứ tự side effects

### 9.1. Gán field của object

Ví dụ:

~~~java
// Minh họa trong class có field int value:
holder().value = compute();
~~~

Java phải đánh giá biểu thức xác định receiver (ở đây **holder()**) trước RHS, với những ràng buộc kiểm tra và gán của field access. Bytecode có thể có các lệnh gọi **holder**, **compute** và **putfield**. Nếu receiver null, hiệu ứng và thời điểm ném **NullPointerException** cần xét theo quy tắc Java của dạng assignment, không chỉ dựa vào tên opcode cuối.

Nếu có **holder().value += compute()**, compiler phải bảo toàn giá trị field cũ và danh tính receiver được đánh giá một lần; **getfield** và **putfield** có thể xuất hiện.

### 9.2. Gán array và kiểm tra chỉ số

Đặc tả Java phân biệt thứ tự kiểm tra ở **simple assignment** và **compound assignment** đến array component.

- Với **array[index] = rhs()** (simple assignment), Java đánh giá array reference và index, rồi đánh giá RHS trước khi thực hiện bước lưu vào array và các kiểm tra runtime gắn với bước gán theo quy tắc tương ứng.
- Với **array[index] += rhs()** (compound assignment), sau khi đánh giá array reference/index, Java thực hiện kiểm tra null/bounds và đọc giá trị cũ của phần tử **trước khi** đánh giá RHS.

Đây là khác biệt có thể quan sát nếu RHS có side effect hoặc ném exception. Không được suy rằng cả hai luôn gọi RHS trước/sau **ArrayIndexOutOfBoundsException** theo một thứ tự giống nhau.

Để phân tích một chương trình cụ thể:

1. Xác định đây là **simple** hay **compound** assignment.
2. Theo dõi array reference và index expressions theo thứ tự.
3. Đánh dấu thời điểm thực hiện null/bounds check và đọc phần tử nếu có.
4. Theo dõi RHS, phép toán và lệnh ghi mảng **xastore** tương ứng.

**Thực hành hữu ích:** biên dịch một ví dụ nhỏ có logging ở index/RHS, rồi dùng **javap -c** xác định **iaload/iastore** và các lời gọi. Đây là trường hợp cần bám ngữ nghĩa JLS, tránh suy diễn chỉ bằng vẻ ngoài của mã nguồn.

## 10. Rẽ nhánh if/else: theo từng cạnh của control-flow graph

Một **if** thường được biến thành **so sánh + nhảy có điều kiện + nhảy vô điều kiện** nếu có else. Ví dụ:

~~~java
static int absLike(int value) {
    if (value >= 0) {
        return value;
    } else {
        return -value;
    }
}
~~~

Một layout bytecode minh họa:

~~~text
  iload value
  iflt NEGATIVE
  iload value
  ireturn
NEGATIVE:
  iload value
  ineg
  ireturn
~~~

Ở JVM, **iflt** lấy một int khỏi stack rồi kiểm tra **value < 0**. Nếu true, nó nhảy đến nhánh NEGATIVE; nếu false, thực thi tiếp phần trả value. Đây là cách diễn giải cùng ngữ nghĩa **if (value >= 0)** mà branch được viết trên trường hợp phủ định.

**Đừng đọc nhầm:** source có dấu **>=**, nhưng opcode có thể là **iflt** để nhảy qua nhánh true. Khi đọc bytecode, phải xem **opcode + target + fall-through path** như một chỉnh thể.

### 10.1. ifeq/ifne cho boolean

Với:

~~~java
// Minh họa:
if (ready) {
    act();
}
~~~

Về mặt computational JVM, **ready** có thể được biểu diễn bằng int, rồi compiler dùng **ifeq** để nhảy qua **act()** khi giá trị false (0). Không phải **ready** ở Java trở thành kiểu số có thể cộng trừ; nó vẫn là boolean theo ngôn ngữ.

### 10.2. if_icmpge khác ifge

- **ifge** lấy **một int** và so nó với 0.
- **if_icmpge** lấy **hai int** và kiểm tra giá trị thứ nhất lớn hơn hoặc bằng giá trị thứ hai.
- **if_acmpeq/if_acmpne** kiểm tra identity/equality của hai reference, không thực thi **equals(...)**.
- **ifnull/ifnonnull** kiểm tra null của một reference.

Khi phân tích điều kiện **i < limit**, bạn có thể gặp **if_icmpge** để nhảy thoát vòng lặp khi điều kiện **không** còn đúng.

## 11. Đọc vòng for: khởi tạo, kiểm tra, thân, cập nhật

Mã nguồn:

~~~java
static int sumBefore(int limit) {
    int sum = 0;
    for (int i = 0; i < limit; i++) {
        sum += i;
    }
    return sum;
}
~~~

Control flow khái quát:

~~~text
START
  |
  v
sum = 0, i = 0
  |
  v
CHECK: i < limit? --- false ---> EXIT: return sum
  |
 true
  v
BODY: sum += i
  |
  v
UPDATE: i++
  |
  +------------------------> CHECK
~~~

Bytecode minh họa với locals **slot 0=limit, slot 1=sum, slot 2=i** (offset thực có thể phụ thuộc compiler):

~~~text
 0: iconst_0
 1: istore_1              // sum = 0
 2: iconst_0
 3: istore_2              // i = 0
 4: iload_2               // CHECK: push i
 5: iload_0               // push limit
 6: if_icmpge 19          // i >= limit -> EXIT
 9: iload_1               // push sum
10: iload_2               // push i
11: iadd                  // sum + i
12: istore_1              // sum = ...
13: iinc 2, 1             // i++
16: goto 4                // loop back to CHECK
19: iload_1
20: ireturn
~~~

Lần theo **sumBefore(4)**:

| Lượt kiểm tra | i | i < 4? | sum trước body | Hoạt động |
| --- | ---: | --- | ---: | --- |
| 1 | 0 | true | 0 | Cộng 0; i thành 1 |
| 2 | 1 | true | 0 | Cộng 1; i thành 2 |
| 3 | 2 | true | 1 | Cộng 2; i thành 3 |
| 4 | 3 | true | 3 | Cộng 3; i thành 4 |
| 5 | 4 | false | 6 | Nhảy đến ireturn |

Giá trị trả về là **6**. Mũi tên **goto 4** mới là lý do nhóm lệnh CHECK/BODY/UPDATE chạy lặp; nếu chỉ đọc từ offset nhỏ đến offset lớn một lần, bạn sẽ dự đoán sai.

### 11.1. for và while thường là cùng một ý tưởng ở bytecode

Với ngữ nghĩa tương đương:

~~~java
int i = 0;
while (i < limit) {
    sum += i;
    i++;
}
~~~

Compiler có thể phát sinh luồng điều khiển gần giống **for**, vì cả hai đều kiểm tra điều kiện trước khi chạy body. **for** chỉ gom initialization, condition, update vào một cú pháp.

Tuy vậy, **scope** của biến **i**, vị trí update và đường đi của **continue** cần được giữ theo đúng ngôn ngữ. Không phải cứ viết lại for thành while theo mắt thường là tương đương trong mọi trường hợp.

## 12. while, do-while, continue và break

### 12.1. while kiểm tra trước, do-while kiểm tra sau

~~~java
int a = 0;
while (a < 0) {
    a++;
}

int b = 0;
do {
    b++;
} while (b < 0);
~~~

Sau hai vòng: **a = 0**, **b = 1**. **while** không chạy body lần nào vì điều kiện false ngay lần đầu; **do-while** chạy body ít nhất một lần rồi mới xét điều kiện.

Sơ đồ:

~~~text
while:
  CHECK? ---- false ----> EXIT
    |
   true
    v
   BODY ----------------> CHECK

do-while:
  BODY
    |
    v
  CHECK? ---- false ----> EXIT
    |
   true
    +-------------------> BODY
~~~

Một compiler có thể tối ưu nhánh nếu biết điều kiện là hằng, nên hãy dự đoán theo semantics trước, sau đó đối chiếu bytecode thực tế.

### 12.2. continue trong for nhảy tới UPDATE, rồi mới CHECK

Với:

~~~java
for (int i = 0; i < 4; i++) {
    if (i == 1) continue;
    System.out.println(i);
}
~~~

Output là **0, 2, 3** trên các dòng riêng. Khi i=1, **continue** bỏ phần còn lại của thân vòng lặp, nhưng vẫn thực hiện **i++** của for trước lần CHECK tiếp theo. Trong bytecode, cạnh **continue** có thể nhảy tới block **UPDATE**.

Ở **while**, continue thường đi đến **CHECK** của vòng bao chứa; nếu tự chuyển code for sang while mà đặt update ở cuối body, **continue** có thể bỏ mất update và gây lặp vô hạn.

### 12.3. break thoát vòng đang được chọn

**break** không nhảy về CHECK; nó đi tới **điểm sau vòng lặp** (hoặc target được chỉ định với labeled break). Với hai vòng lồng nhau, **break** không nhãn thoát vòng trong cùng; **break outer;** có thể thoát vòng gắn label **outer**.

**Labeled continue** nhảy sang chu kỳ tiếp theo của vòng lặp được gắn label tương ứng (với các yêu cầu đúng cú pháp JLS). Khi đọc bytecode không thấy “tên label Java” một cách tất yếu; chỉ thấy các target offsets đã được compiler tính.

### 12.4. finally có thể làm đường đi phức tạp hơn

Nếu **break**, **continue** hoặc **return** nằm trong một vùng **try/finally**, Java vẫn phải thực hiện các bước **finally** thích hợp khi rời vùng, trừ các trường hợp đặc biệt theo đặc tả. Compiler có thể sinh thêm control-flow và exception handlers. Khi có try/finally, không nên giải nghĩa một **goto** đơn lẻ như toàn bộ hành vi của break/continue mà bỏ qua các block cleanup.

## 13. &&, || và &: nhìn nhánh để thấy short-circuit

Toán tử logic Java:

| Toán tử | Đánh giá RHS khi nào? | Kết quả |
| --- | --- | --- |
| **a && b** | Chỉ khi a là true | AND logic có short circuit |
| **a || b** | Chỉ khi a là false | OR logic có short circuit |
| **a & b** với boolean | Luôn đánh giá cả hai vế | AND logic không short circuit |
| **a | b** với boolean | Luôn đánh giá cả hai vế | OR logic không short circuit |
| **a ^ b** với boolean | Luôn đánh giá cả hai vế | XOR logic |

Ví dụ:

~~~java
// Minh họa:
if (isReady() && loadData()) {
    process();
}
~~~

Một control-flow tương đương:

~~~text
call isReady()
  if false -> END
call loadData()
  if false -> END
call process()
END:
~~~

Nếu **isReady()** trả false, lệnh gọi **loadData()** phải bị bỏ qua. Compiler thường hiện thực bằng instruction kiểu **ifeq/ifne**; không thể thay tùy tiện **&&** bằng **iand** sau khi đã đánh giá hai vế vì điều đó có thể làm RHS chạy trái ngữ nghĩa source.

Trong biểu thức không short circuit như **isReady() & loadData()**, hai bên đều được đánh giá (trái rồi phải). Compiler có thể sử dụng **iand** cho giá trị boolean tính toán qua int, hoặc các lệnh tương đương khác, miễn kết quả và side effects được bảo toàn.

**Tránh một lỗi nguy hiểm:** trong điều kiện **obj != null && obj.isActive()**, toán tử **&&** bảo vệ việc gọi method trên null. Đổi thành **&** có thể gây **NullPointerException**.

## 14. Toán tử ba ngôi và switch

### 14.1. condition ? trueValue : falseValue

~~~java
int result = score >= 60 ? passValue() : failValue();
~~~

Java đánh giá **score >= 60**, sau đó chỉ đánh giá **một trong hai nhánh**. Bytecode có thể dùng một lệnh điều kiện để nhảy tới block tương ứng, rồi **goto** gộp về điểm chung, ví dụ:

~~~text
evaluate condition
if false -> ELSE
call passValue
goto JOIN
ELSE:
call failValue
JOIN:
store result
~~~

Hai nhánh không được gọi cùng lúc để “rồi chọn kết quả”; side effects/exception phải theo đúng một nhánh được chọn.

### 14.2. switch có nhiều cách phát mã

Với **switch** trên giá trị kiểu int hoặc các dạng tương ứng, bytecode có thể có **tableswitch** hoặc **lookupswitch**:

- **tableswitch** hữu ích cho dải giá trị gần liên tiếp, có bảng offset nhảy.
- **lookupswitch** dùng các cặp match-value và offset target.
- Với string switch, enum switch hoặc pattern/switch expressions, compiler có thể sinh các bước xử lý bổ sung.

Cần đọc chính instruction **tableswitch/lookupswitch** và mọi target block, không đoán thứ tự chạy case theo thứ tự case xuất hiện trong disassembly. **break** trong switch và **break** trong vòng lặp có target khác nhau theo cấu trúc điều khiển.

## 15. Ví dụ runnable số 2: bytecode gọn để đọc từng lệnh

Tạo tệp **BytecodeLoopLab.java**:

~~~java
public class BytecodeLoopLab {
    static int multiplyAdd(int a, int b) {
        return (a + b) * 2;
    }

    static int sumBefore(int limit) {
        int sum = 0;
        for (int i = 0; i < limit; i++) {
            sum += i;
        }
        return sum;
    }

    static int sign(int value) {
        return value > 0 ? 1 : -1;
    }

    public static void main(String[] args) {
        System.out.println("multiplyAdd=" + multiplyAdd(2, 3));
        System.out.println("sumBefore=" + sumBefore(4));
        System.out.println("signZero=" + sign(0));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 BytecodeLoopLab.java
java BytecodeLoopLab
javap -c -p BytecodeLoopLab
~~~

**Stdout chính xác của lệnh java (không gồm phần javap):**

~~~text
multiplyAdd=10
sumBefore=6
signZero=-1
~~~

Với **multiplyAdd**, một trình biên dịch **javac** phổ biến tạo dạng:

~~~text
0: iload_0
1: iload_1
2: iadd
3: iconst_2
4: imul
5: ireturn
~~~

Lần theo các trạng thái operand stack:

| Offset | Instruction | Stack sau lệnh |
| ---: | --- | --- |
| 0 | iload_0 | [2] |
| 1 | iload_1 | [2, 3] |
| 2 | iadd | [5] |
| 3 | iconst_2 | [5, 2] |
| 4 | imul | [10] |
| 5 | ireturn | trả 10 |

Đây là bytecode mẫu rất phù hợp để luyện đọc stack vì không có side effects ngoài và không có branch.

Với **sumBefore**, hãy đối chiếu dãy lệnh **iload**, **if_icmpge**, **iadd**, **istore**, **iinc**, **goto** đã trình bày ở mục 11. Với **sign**, tìm nhánh kiểu **ifle** tới trường hợp zero/negative, lệnh nạp 1 hay -1 và chỗ join/return. Compiler có thể phát sinh:

~~~text
load value
if value <= 0 -> NEGATIVE
push 1
goto RETURN
NEGATIVE:
push -1
RETURN:
ireturn
~~~

Điều đáng học là **hai đường đi khác nhau hội tụ tại một điểm trả về**, không phải học thuộc offset cố định của compiler.

## 16. Phân tích một trường hợp biểu thức khó bằng bảng trạng thái

Xét:

~~~java
// Minh họa bên trong một phương thức:
int i = 1;
int value = i++ + ++i * i;
~~~

Các bước theo JLS:

| Bước | Hành động | i sau bước | Giá trị toán hạng được giữ |
| --- | --- | ---: | --- |
| 1 | Đánh giá vế trái của dấu +: **i++** | 2 | Vế trái **+** giữ **1** |
| 2 | Đánh giá vế trái của dấu *: **++i** | 3 | Vế trái **\*** giữ **3** |
| 3 | Đánh giá vế phải dấu *: đọc **i** | 3 | Vế phải **\*** là **3** |
| 4 | Tính phép nhân **3 * 3** | 3 | Kết quả nhân **9** |
| 5 | Tính phép cộng **1 + 9** | 3 | **value = 10** |

Vì vậy kết quả **value = 10**, **i = 3**. Một cách nhìn stack ở mức ý tưởng:

~~~text
i++     -> push 1, i thành 2          stack [1]
++i     -> push 3, i thành 3          stack [1, 3]
i       -> push 3                     stack [1, 3, 3]
imul    -> push 9 thay 3,3            stack [1, 9]
iadd    -> push 10 thay 1,9           stack [10]
istore  -> value = 10                 stack []
~~~

Dù biểu thức hợp lệ và có kết quả xác định, dạng viết nhiều thay đổi trên cùng một biến là kém rõ ràng cho code production. Phân tích bytecode giúp xác nhận quy tắc, còn viết code dễ đọc giúp tránh phải phân tích những trường hợp này khi sửa lỗi.

## 17. Trường hợp thứ tự đánh giá và tối ưu compiler

### 17.1. Không có ánh xạ một-một từ dòng Java sang lệnh JVM

Đoạn source:

~~~java
int answer = 10 + 20;
~~~

Có thể được compiler gộp thành một hằng **30** thay vì bytecode lần lượt đẩy 10, đẩy 20 rồi **iadd**. Nếu mã không có side effects, giữ nguyên kết quả là đủ trong phạm vi tối ưu hợp lệ.

Ngược lại:

~~~java
int answer = next("A", 10) + next("B", 20);
~~~

Không thể tùy ý hoán đổi hai lời gọi khi chúng in ra những dòng khác nhau; side effects phải phản ánh evaluation order của Java.

### 17.2. Javac bytecode và JIT machine code là hai tầng

**javap -c** đọc **bytecode trong class file**. JVM có thể interpret hoặc JIT compile các method nóng sang mã máy, tối ưu nội bộ, inline method, giữ giá trị trong thanh ghi hoặc xóa thao tác không ảnh hưởng hành vi quan sát. Vì vậy:

- Dùng **javap** để hiểu định dạng và control flow của bytecode **đã biên dịch**.
- Dùng kết quả chạy và đặc tả Java để kiểm tra **ngữ nghĩa quan sát được**.
- Không dùng javap như hình ảnh chính xác của các lệnh CPU mà JIT đang chạy.
- Không coi một dạng bytecode của riêng javac phiên bản X là quy tắc bắt buộc của JLS.

### 17.3. Lỗi runtime thay đổi đường đi

Các instructions như **idiv**, **iaload**, **getfield** hoặc lời gọi method có thể ném exception. Khi đó PC không đơn giản đi tiếp offset kế tiếp; JVM tìm exception handler thích hợp theo exception table, hoặc tiếp tục unwind frame. Vì vậy “đọc thẳng từ trên xuống” có thể sai kể cả khi không thấy lệnh **goto** gần đó.

Nếu có **finally**, bytecode có thể phức tạp hơn do cleanup logic. Để dự đoán thứ tự thực thi, phải xét **mọi cạnh thường lẫn cạnh exception**.

### 17.4. Không dùng thứ tự bytecode để dự đoán lịch chạy giữa threads

JLS cho thứ tự đánh giá biểu thức của **một thread** theo ngữ nghĩa chương trình. Bytecode của một method không chứng minh thứ tự xen kẽ giữa nhiều threads là cố định. Muốn suy luận kết quả concurrent code phải xét **Java Memory Model**, đồng bộ hóa và quan hệ happens-before. Tránh suy từ PC của thread A rằng thread B sẽ chờ A đến một offset nhất định.

## 18. Quy trình đọc bytecode để dự đoán thứ tự chính xác

Thay vì thử đoán cả method, thực hiện theo vòng lặp phân tích sau:

1. **Biên dịch mã nguồn đúng phiên bản**, lưu class file và dùng **javap -c -p** để lấy instruction offsets.
2. **Xác định method descriptor** và những local slots đầu tiên dành cho **this**/tham số; hiểu kiểu giá trị (int, long, reference...).
3. **Đánh dấu các nguồn side effect:** **invoke...**, **putfield/putstatic**, **xastore**, I/O, phương thức tự tăng, monitor và những thao tác có thể ném exception.
4. **Lập bảng** gồm **PC, local variables, operand stack, nhánh được chọn, output/side effects**. Khởi tạo trạng thái từ input thực tế.
5. **Mô phỏng từng instruction**: đọc/ghi stack đúng thứ tự; chú ý toán tử không giao hoán như trừ, chia; cập nhật locals khi gặp store hoặc iinc.
6. **Đối với if/loop**, tính điều kiện rồi chuyển PC sang target hoặc fall-through; không đi qua cả hai nhánh.
7. **Với gán compound/++**, đánh dấu old value, new value và số lần đánh giá biểu thức receiver/index; đừng nhầm stack value với giá trị variable hiện tại.
8. **Theo dõi exceptions** khi cần: thao tác gây lỗi có thể hủy việc đánh giá các biểu thức phía sau hoặc chuyển vào handler.
9. **Ghi stdout theo đúng thời điểm gọi println**, sau khi biểu thức argument của nó đã được đánh giá.
10. **Đối chiếu chương trình chạy**, cuối cùng giải thích bằng **quy tắc JLS** và bytecode quan sát được. Nếu khác, kiểm tra lớp biên dịch, JDK, input, thread/concurrency và các side effects bỏ sót.

Bảng sườn để tự điền:

| PC | Instruction | Locals trước/sau | Stack trước/sau | Branch target | Side effect/output |
| --- | --- | --- | --- | --- | --- |
| offset hiện tại | opcode | giá trị thay đổi? | lấy/đẩy phần tử gì? | nhảy hay fall-through? | in, ghi field/array, gọi method? |

Bảng này đặc biệt hiệu quả với code gồm các lệnh **iinc** và các nhánh nhảy ngược: sau mỗi lần **goto**, bạn quay về đúng PC mục tiêu với local variables đã được cập nhật.

## 19. Những nhầm lẫn phổ biến

1. **“Lệnh hiện ở dòng dưới javap chắc chắn chạy sau lệnh dòng trên.”** Không đúng nếu điều khiển nhảy qua hoặc lặp lại instruction.
2. **“Độ ưu tiên toán tử là thứ tự gọi method.”** Không đúng; **left() + right()*4** vẫn đánh giá left() trước right().
3. **“i++ và ++i là như nhau vì đều tăng i.”** Sai khi giá trị biểu thức được dùng: postfix trả cũ, prefix trả mới.
4. **“iinc đẩy giá trị mới lên stack.”** Không; iinc trực tiếp thay local, không có operand-stack effect như iload.
5. **“istore đọc local.”** Ngược lại; **iload** đọc local rồi push, **istore** pop rồi ghi local.
6. **“&& chỉ là phép & được viết khác.”** Không; **&&** short circuit, **&** trên boolean đánh giá cả hai vế.
7. **“Trong vòng for, continue bỏ luôn i++.”** Không; continue nhảy tới bước update rồi condition, khi đây là vòng for tương ứng.
8. **“if (a >= b) luôn tạo if_icmpge.”** Không; compiler có thể dùng nhánh phủ định **if_icmplt** để nhảy qua body.
9. **“Một câu lệnh gán compound được giải nghĩa bằng cách chép nguyên văn bên trái hai lần.”** Sai với receiver/index có side effects; Java bảo đảm vế trái được đánh giá một lần.
10. **“Một dòng source = một opcode.”** Không; compiler có thể tạo nhiều instruction, gộp hằng hoặc phát mã cho helper/exception table.
11. **“Giá trị trên operand stack là chính biến trong locals.”** Không; stack có thể giữ giá trị cũ trong khi local đã được cập nhật.
12. **“Output của một chương trình đa luồng có thể suy hết từ javap của một thread.”** Không; thứ tự giữa threads cần phân tích đồng bộ và memory model.

## 20. Bài tập dự đoán có đáp án

**Bài 1 — Prefix và postfix**

~~~java
int x = 2;
int y = x++ + ++x;
System.out.println("x=" + x + ",y=" + y);
~~~

**Đáp án:** **x=4,y=6**. Vế trái trả 2 rồi x=3; vế phải tăng x=4 rồi trả 4; tổng 6.

**Bài 2 — Thứ tự đánh giá**

~~~java
int n = 1;
int result = (n = 5) * n;
System.out.println("n=" + n + ",result=" + result);
~~~

**Đáp án:** **n=5,result=25**. Phép gán bên trái hoàn tất trước khi vế phải đọc n.

**Bài 3 — Gán compound trên mảng**

~~~java
int[] a = {4, 9};
int k = 0;
a[k++] += 2;
System.out.println("a0=" + a[0] + ",k=" + k);
~~~

**Đáp án:** **a0=6,k=1**. Index được lấy ở giá trị cũ 0; RHS cộng vào phần tử đó.

**Bài 4 — Continue**

~~~java
int sum = 0;
for (int i = 0; i < 4; i++) {
    if (i == 2) continue;
    sum += i;
}
System.out.println(sum);
~~~

**Đáp án:** **4** (0+1+3). Khi i=2, continue vẫn đi qua for-update để tăng i rồi kiểm tra lại.

**Bài 5 — Do-while**

~~~java
int a = 0;
do {
    a++;
} while (a < 0);
System.out.println(a);
~~~

**Đáp án:** **1**, bởi body chạy một lần trước condition.

**Bài 6 — Đọc nhánh phủ định**

Bytecode minh họa:

~~~text
iload_0
iconst_5
if_icmplt 12
iconst_1
ireturn
12: iconst_0
ireturn
~~~

**Đáp án:** Method trả **1** khi tham số **>= 5**, trả **0** khi tham số **< 5**. Opcode **if_icmplt** nhảy sang nhánh trả 0, nên nó là điều kiện phủ định nhánh trả 1.

**Bài 7 — Đánh giá ngắn mạch**

~~~java
int n = 0;
boolean ok = (n != 0) && (10 / n > 1);
System.out.println(ok);
~~~

**Đáp án:** In **false**, không ném **ArithmeticException**, vì vế phải của **&&** không được đánh giá khi n=0. Nếu đổi **&&** thành **&**, phép chia sẽ được đánh giá và lỗi xảy ra.

**Bài 8 — Operand stack**

Khi stack từ đáy tới đỉnh là **[8, 2]**, chạy **idiv** cho giá trị nào?

**Đáp án:** **4**, vì int thứ nhất/giá trị nằm dưới đỉnh là dividend 8, đỉnh stack là divisor 2. Không phải 2/8.

**Bài 9 — Vòng for trong javap**

Bạn thấy chuỗi instruction gồm **if_icmpge 25**, sau đó body, **iinc**, **goto 4**, rồi **25: ireturn**. Khi điều kiện so sánh **i >= limit** đúng thì chuyện gì xảy ra?

**Đáp án:** PC nhảy thẳng đến **offset 25** để trả về; nếu sai thì chạy body, iinc và goto quay về offset 4.

**Bài 10 — Giới hạn phân tích**

Bạn thấy **javap -c** của method có hai lệnh gọi **A()**, **B()** theo thứ tự lưu, nhưng method là callback bất đồng bộ và A/B có thể tạo thread. Có đủ cơ sở nói mọi log từ B luôn sau mọi log từ A không?

**Đáp án:** Không. Thứ tự đánh giá lời gọi trong thread ban đầu có quy tắc, còn hoạt động bên trong các thread khác có thể xen kẽ. Phải phân tích đồng bộ/happens-before riêng.

## 21. Tài liệu đặc tả

- **Java Language Specification SE 17, §15.7 — Evaluation Order**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.7
- **JLS §15.14–§15.15 — Postfix, Prefix Expressions**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.14
- **JLS §15.23–§15.24 — Conditional-And / Conditional-Or Operators**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.23
- **JLS §15.26 — Assignment Operators**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.26
- **JLS §14 — Blocks, Statements, and Patterns (for, while, break, continue)**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html
- **JVMS SE 17, §2.6 — Frames; §2.11 — Instruction Set Summary**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html
- **JVMS SE 17, §6.5 — Instructions (iload, istore, iinc, branch, invoke, dup, array/field)**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html

**Ghi nhớ:** muốn dự đoán thứ tự thực thi, đọc bytecode như **một luồng trạng thái** gồm **PC + locals + operand stack + side effects + nhánh**, chứ không đọc như danh sách lệnh chạy tuần tự đúng một lần. Java bảo đảm evaluation order quan sát được; javac hiện thực bằng các lệnh load/store, phép toán, nhảy và cấu trúc stack. Khi gặp **++**, **+=**, **&&**, loop và array assignment, luôn theo dõi **giá trị cũ, giá trị mới, số lần đánh giá và đường nhảy**. Khi thiếu một trong các yếu tố này, rất dễ suy ra sai output dù bạn nhận diện đúng từng opcode.
