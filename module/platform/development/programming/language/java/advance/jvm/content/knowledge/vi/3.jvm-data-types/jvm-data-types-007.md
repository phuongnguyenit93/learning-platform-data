# Kiểu `returnAddress` và lý do cần nhận diện bytecode lịch sử

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích `returnAddress` là một **kiểu nguyên thủy đặc biệt của JVM**, khác với `int` và `reference`, không có kiểu tương ứng trong mã nguồn Java.
- Đọc được luồng điều khiển `jsr`/`jsr_w` → `astore` → `ret` từng dùng để thực hiện khối `finally` trong bytecode cũ.
- Phân biệt `ret` (quay về bên trong cùng một phương thức) với `return`/`ireturn`/`areturn` (kết thúc lời gọi phương thức).
- Nhớ ranh giới **class-file version ≤ 50.0** và **≥ 51.0**, biết khi nào legacy opcodes bị cấm.
- Dùng `javap` nhận diện class file cũ mà không cần tạo bytecode bất hợp lệ hoặc phụ thuộc trình biên dịch Java cổ.

**Thông điệp chính:** `returnAddress` vẫn được mô tả trong Java Virtual Machine Specification (JVMS) để giải thích cách các class file cũ biểu diễn luồng điều khiển. Nó **không phải** một kiểu để lập trình viên Java viết trong source và cũng **không phải** kiểu trả về của phương thức Java.

## 1. `returnAddress` đứng ở đâu trong hệ kiểu JVM?

Theo JVMS §2.2–2.3, JVM có các kiểu nguyên thủy, kiểu tham chiếu và nhiều cơ chế biểu diễn giá trị runtime. Trong nhóm nguyên thủy có những kiểu số quen thuộc như `int`, `long`, `float`, `double`; kiểu `boolean` có hỗ trợ đặc thù; và **`returnAddress`** là một trường hợp rất riêng.

| Kiểu JVM | Giá trị minh họa | Liên hệ mã nguồn Java | Vai trò |
| --- | --- | --- | --- |
| `int` | `42` | `int` và các phép tính dùng `int` trên operand stack | Tính toán số nguyên |
| `reference` | tham chiếu đến object/array hoặc `null` | Object, array, interface, v.v. | Truy cập dữ liệu kiểu tham chiếu |
| **`returnAddress`** | vị trí opcode của một lệnh bytecode trong cùng method | **Không có kiểu Java tương ứng** | Ghi nhớ vị trí cần tiếp tục sau lời gọi bytecode subroutine cũ |

Các thuộc tính cần nắm:

1. `returnAddress` là kiểu nguyên thủy **được định nghĩa ở cấp máy ảo**; không phải một Java class, interface, pointer kiểu C, cũng không phải một subclass của `Object`.
2. Giá trị biểu thị **vị trí opcode của một lệnh JVM** dùng để tiếp tục chạy sau `jsr` hoặc `jsr_w`. Nó không phải chuỗi, số thứ tự dòng source, địa chỉ email hay địa chỉ bộ nhớ mà ứng dụng Java được phép chỉnh sửa.
3. Không thể khai báo trong Java: `returnAddress x;` không phải cú pháp kiểu dữ liệu Java hợp lệ. Không có phép `new returnAddress(...)`, cast thông thường, API Java để cộng/trừ hay serialize giá trị này.
4. Nó thuộc **category 1** trong hệ kiểu tính toán của JVM, chiếm **một ô** trên operand stack hoặc trong local variables khi dùng. `long` và `double` thuộc category 2, chiếm hai ô; **category không nói rằng returnAddress là một `int`**.
5. JVM kiểm soát nơi `returnAddress` được tạo, lưu và tiêu thụ; chương trình đang chạy không được sửa giá trị địa chỉ này bằng các phép toán thông thường.

JVMS nói “pointer to the opcode of a JVM instruction” ở mức **mô hình trừu tượng**. Đừng suy ra phải là một con trỏ native 32-bit/64-bit được Java code nhìn thấy. Kỹ thuật biểu diễn nội bộ do cách triển khai JVM quyết định.

### Tại sao `returnAddress` không phải `reference`?

Cả hai đều có kích thước tính toán category 1, nhưng **ngữ nghĩa và phép toán hợp lệ khác nhau**. Một `reference` có thể trỏ tới object/array hoặc là `null`; một `returnAddress` là dấu mốc điều khiển của bytecode subroutine. Bạn không thể dùng `getfield`, `invokevirtual`, `ifnull` hoặc `aload` như thể nó là một Java object reference. Đây là khác biệt về **kiểu**, không đơn thuần cách gọi.

Không nên hiểu từ “return” trong tên `returnAddress` là kiểu giá trị trả về của Java method. Các method Java vẫn khai báo kiểu trả về theo ngôn ngữ và method descriptor; `returnAddress` không phải kiểu được phép khai báo trong field/method descriptor thông thường.

## 2. Mô hình stack frame và địa chỉ quay lại

Trong một phương thức đang thực thi, JVM frame có ít nhất:

- **Local variables**: các slot lưu tham số và biến cục bộ/giá trị tạm.
- **Operand stack**: nơi bytecode lấy và đặt toán hạng.
- Thông tin phục vụ linking và điều khiển; mỗi thread có **PC register** xác định vị trí thực thi JVM instruction khi đang chạy Java bytecode.

Trong bytecode lịch sử, `jsr` gọi một **subroutine bên trong cùng một method**. Nó **không tạo một Java method invocation** mới như `invokestatic` hay `invokevirtual` và không tự mở frame của một phương thức Java riêng. Nó tạo dấu mốc trở về là kiểu `returnAddress`, đẩy dấu mốc lên operand stack và nhảy tới subroutine. Subroutine giữ địa chỉ đó trong local variable. `ret` lấy địa chỉ từ local variable và cập nhật luồng điều khiển để tiếp tục tại lệnh ngay sau lời `jsr` tương ứng.

~~~text
                  [Cùng một method / JVM frame]
              local variables        operand stack
                     |                      |
Caller:              |                      |
   ...               |                      |
   jsr Lfinally -----+--------------------> | returnAddress = next instruction
      |                                     |
      +-------------- jumps to Lfinally     |
                                            v
Lfinally:                             astore 2
                                      pop returnAddress
                       local[2] <-----------+
      ... cleanup ...     |
      ret 2 <-------------+
          |
          v
   [instruction just after jsr]
~~~

Sơ đồ chỉ diễn tả **giá trị luồng điều khiển**, không có nghĩa người viết Java được truy cập trực tiếp stack frame hay PC register.

## 3. Ba lệnh cốt lõi: `jsr`, `astore` và `ret`

| Bytecode | Tác động | Ghi chú |
| --- | --- | --- |
| `jsr target` | Đẩy `returnAddress` của lệnh ngay sau `jsr` lên operand stack rồi nhảy tới target | Branch offset ngắn, opcode `0xa8` |
| `jsr_w target` | Tương tự `jsr` với branch offset rộng hơn | Opcode `0xc9` |
| `astore n` / `astore_<n>` | Lấy một `reference` **hoặc** `returnAddress` trên đỉnh operand stack và ghi vào local slot `n` | Dùng để cất địa chỉ trở về trong subroutine |
| `ret n` | Đọc `returnAddress` trong local slot `n`, chuyển PC tới địa chỉ đó | Không lấy giá trị từ operand stack; opcode `0xa9` |
| `return` | Trả về từ method `void` tới caller của method | Không cùng chức năng với `ret` |
| `ireturn` / `areturn` | Trả giá trị của một method cho method caller | Không dùng `returnAddress` |

### Diễn biến chính xác ở mức operand stack

Giả sử opcode `jsr` nằm tại offset giả định 20 và lệnh kế tiếp bắt đầu tại offset 23:

1. `jsr Lcleanup` **đẩy returnAddress tương ứng offset 23** lên operand stack.
2. JVM chuyển tới opcode đầu tiên tại `Lcleanup` trong **cùng method**.
3. `astore_2` lấy `returnAddress` đang trên đỉnh stack và lưu vào `local[2]`.
4. Sau phần cleanup, `ret 2` đọc `local[2]` và chuyển PC trở về offset 23.
5. Lệnh tại offset 23 tiếp tục. Nếu đó là `return` hoặc `ireturn`, khi ấy **phương thức Java** mới hoàn tất.

Không được viết `aload_2` để đọc lại `returnAddress`. JVMS §6.5 mô tả rõ **`astore` nhận returnAddress, nhưng `aload` không được load returnAddress**; sự bất đối xứng này là chủ ý. `ret` mới là lệnh dùng giá trị từ local variable để trở về.

Đặc biệt, `ret` **không có cùng nghĩa** với `return`. Nếu method có nhiều điểm gọi chung một finally subroutine, `ret` quay về đúng vị trí sau `jsr` đã gọi nó. Ngược lại, `return` kết thúc frame của method và trở lại method caller.

## 4. Vì sao bytecode cũ dùng `returnAddress` cho `finally`?

Một khối `finally` thường phải được thực thi trước khi luồng điều khiển rời khỏi `try` theo nhiều ngả: hoàn tất bình thường, `return`, một số bước chuyển điều khiển như `break`/`continue`, hoặc có exception. Một cách tổ chức bytecode **trước đây** là biên dịch nội dung finally thành **subroutine dùng chung** ở cuối method và gọi nó từ các vị trí thoát bằng `jsr`; địa chỉ quay lại nằm trong `returnAddress`.

Ví dụ mã nguồn Java minh họa:

~~~java
void work() {
    try {
        doWork();
    } finally {
        release();
    }
}
~~~

Dưới đây là **bytecode giả lập dạng sơ đồ** minh họa lối biên dịch cũ; **không phải class file hoàn chỉnh, không được đưa nguyên vào `javap` hoặc assembler để chạy**. Các label tượng trưng thay cho offset thực tế, phần exception table bị lược bỏ:

~~~text
Ltry:
    aload_0
    invokevirtual doWork()
    jsr Lfinally            ; ghi địa chỉ lệnh kế tiếp vào returnAddress
    return                  ; đường đi bình thường: method kết thúc sau finally

LcatchAll:                  ; handler bắt exception của try
    astore_1                ; local[1] = Throwable, KIỂU reference
    jsr Lfinally            ; lần này returnAddress trỏ tới aload_1
    aload_1
    athrow                  ; ném lại exception sau finally

Lfinally:
    astore_2                ; local[2] = returnAddress, KHÔNG PHẢI Throwable
    aload_0
    invokevirtual release()
    ret 2                   ; quay lại sau đúng jsr đã gọi
~~~

Cùng một vùng bytecode `Lfinally` có thể được gọi từ nhánh bình thường và nhánh exception. Vì vậy nó cần **địa chỉ trở về tương ứng từng lần gọi** thay vì cố định một chỗ quay lại. Đây chính là mục đích của `returnAddress`.

### Đọc kỹ hai local slots trong sơ đồ

- `local[1]` giữ **exception reference**; `aload_1` hợp lệ để lấy lại exception trước `athrow`.
- `local[2]` giữ **returnAddress**; `aload_2` sẽ không hợp lệ nếu slot đang chứa kiểu này. `ret 2` đọc nó theo ngữ nghĩa riêng.
- `Lfinally` là **subroutine nội bộ cùng một method**, không phải hàm Java có tên `finally`, không phải lời gọi `invokestatic` và không tạo frame method mới.
- Nếu `release()` tự ném exception, đường quay về qua `ret` có thể không diễn ra; đây là luật exception thông thường, không có bảo đảm `finally` sẽ hoàn tất bình thường.

### Điều gì xảy ra khi `try` có `return`?

Trong cách biên dịch lịch sử, compiler có thể:

1. Lưu giá trị định trả về vào local variable.
2. Gọi `finally` subroutine qua `jsr`.
3. Khi `ret` quay về, khôi phục giá trị trả về rồi dùng lệnh kết thúc method như `ireturn`.

Như vậy **`ret` quay về phần bytecode tiếp tục xử lý việc return**, còn `ireturn` mới đưa giá trị về method caller. Hai kiểu “trở về” nằm ở **hai tầng điều khiển khác nhau**.

## 5. Điểm ranh giới lịch sử: class-file version 50 và 51

Đây là quy tắc tương thích quan trọng nhất khi đọc bytecode cũ.

| Class-file major | Gắn với release | Tình trạng `jsr`/`jsr_w`/`ret` theo JVMS |
| --- | --- | --- |
| 45–49 | Các release Java cũ tới Java 5 | Có thể xuất hiện khi bytecode thỏa các quy tắc xác minh lịch sử |
| **50** | **Java 6** | **Vẫn có thể xuất hiện** trong class file hợp lệ |
| **51** | **Java 7** | **Bị cấm** trong `Code` attribute |
| 52 | Java 8 | **Bị cấm** |
| 61 | Java 17 | **Bị cấm** |
| 65 | Java 21 | **Bị cấm** |
| 69 | Java 25 | **Bị cấm** |
| 70 | Java 26 | **Bị cấm** |

Theo **JVMS §4.9.1 (Static Constraints)**: với `class` file **version 51.0 hoặc cao hơn**, các opcode `jsr`, `jsr_w` và `ret` **không được xuất hiện** trong mảng code của phương thức. Điều cấm này tính theo **class-file version**, không phải chỉ dựa trên tên JVM đang chạy.

Cần tách ba ý:

- **Các opcode còn được tài liệu JVMS mô tả**: đúng, để xác định nghĩa và giải thích class file cũ.
- **Class file mới major ≥ 51 được phép chứa chúng**: **sai**; vi phạm static constraints.
- **Một JVM hiện đại có thể gặp class file major ≤ 50 hợp lệ**: có thể, tùy phiên bản class file còn được JVM đó hỗ trợ và các quy tắc xác minh; **không nên suy ra mọi JVM đều chạy mọi binary cổ**.

Không nhầm với quy tắc “Java 7 đã xoá opcode khỏi mọi định nghĩa JVM”: các opcode vẫn được liệt kê trong JVMS, còn quy tắc class-file format **hạn chế nơi chúng có thể xuất hiện**.

### Liên hệ cơ chế verifier

Các cấu trúc `jsr`/`ret` có luồng điều khiển phức tạp: cùng một subroutine có thể phục vụ nhiều đường rẽ và phải quay về địa chỉ hợp lệ. Verifier cần bảo đảm kiểu tại local slots/operand stack và tính hợp lệ của subroutine call chain.

JVMS §4.9.1 còn có ràng buộc về việc không được load `returnAddress` bằng lệnh thông thường, số lần có thể quay về, giới hạn liên quan đến chuỗi subroutine để tránh những luồng điều khiển không hợp lệ. Trong các bản class file cũ, quy tắc **verification by type inference** có vai trò riêng; từ class-file major 50 có cơ chế **type checking** dựa trên stack-map frames, với một trường hợp tương thích của version 50.0.

Bạn không cần thuộc toàn bộ luật verifier để học loại dữ liệu này, nhưng phải hiểu rằng **không phải đặt một `jsr` và `ret` bất kỳ là có bytecode hợp lệ**. Không nên “thử” bằng cách sửa vài byte trong class file thật rồi coi crash/lỗi verify là bằng chứng JVM có bug.

### Vì sao compiler hiện đại không phát sinh `jsr`/`ret`?

Compiler Java hiện nay thường hạ `try`/`finally` thành các đường thực thi chứa mã xử lý `finally` cần thiết và exception handlers thích hợp, thay vì gọi một subroutine chung bằng `jsr`. Cách phát sinh bytecode cụ thể là quyết định của compiler, nhưng **ràng buộc major ≥ 51** bảo đảm code của class version mới **không có ba opcode legacy**.

Đừng suy ra mã `finally` luôn được duplicate đúng một số lần cố định hoặc bytecode giống hệt mọi bản `javac`: số nhánh, return value, exception table và phép tối ưu có thể làm hình dạng code khác nhau.

## 6. Thực hành chạy được với Java 17+: finally hiện đại

Mục tiêu bài thực hành: quan sát **ngữ nghĩa của `finally` khi return và exception**, sau đó xem bytecode để thấy không cần `jsr`/`ret`. Tạo file `FinallyFlow.java`:

~~~java
public class FinallyFlow {
    static int run(boolean fail) {
        try {
            System.out.println("try " + fail);
            if (fail) {
                throw new IllegalStateException("boom");
            }
            return 7;
        } finally {
            System.out.println("finally " + fail);
        }
    }

    public static void main(String[] args) {
        System.out.println("result=" + run(false));
        try {
            run(true);
        } catch (IllegalStateException ex) {
            System.out.println("caught=" + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac FinallyFlow.java
java FinallyFlow
~~~

**Stdout chính xác:**

~~~text
try false
finally false
result=7
try true
finally true
caught=boom
~~~

Giải thích:

- Nhánh `run(false)`: `return 7` được tính toán nhưng `finally` thực thi trước khi method trả kết quả cho caller.
- Nhánh `run(true)`: ném `IllegalStateException`, `finally` vẫn chạy trên đường ngoại lệ rồi exception truyền ra caller và được `catch` xử lý.
- Đây là **ngữ nghĩa Java hiện đại**, không chứng minh compiler hiện nay sinh `jsr`; ngược lại, class do `javac` 17 biên dịch có major 61 và **không được có `jsr`/`ret`**.

Xem disassembly và class version:

~~~bash
javap -c -p FinallyFlow
javap -verbose FinallyFlow
~~~

Trong `javap -verbose`, tìm dòng `major version: 61` nếu dùng đúng `javac` 17 không thêm option `--release`/`--target` khác; khi dùng JDK 21 mặc định là 65, JDK 25 là 69, v.v. Trong `javap -c -p`, xem nhánh thường, exception table và các đoạn gọi `println` để thực hiện `finally`. **Bạn không nên thấy opcode `jsr`/`jsr_w`/`ret` trong class-file major ≥ 51 được compiler hợp lệ tạo ra**.

### Nếu muốn biên dịch cho bản Java thấp hơn

`javac --release 8 FinallyFlow.java` (trên JDK có hỗ trợ target 8) tạo class file tương ứng **major 52**, vẫn cấm `jsr`/`ret`. Hạ `--release` xuống 8 **không tái hiện cơ chế `finally` kiểu Java 1.4**. Nhiều JDK hiện đại cũng không còn hỗ trợ `--release 6` hoặc `-target 6`; đừng hướng người học dùng lệnh không được JDK hiện tại chấp nhận.

Muốn xem `jsr`/`ret` thật, hãy lấy **một class file lịch sử có nguồn gốc rõ ràng** hoặc tài liệu disassembly mẫu của JVMS, kiểm tra major version của file đó rồi đọc ở chế độ phân tích. Không cần sinh lại bằng compiler lỗi thời để hiểu nguyên tắc.

## 7. Cách nhận diện an toàn trong file `.class` lịch sử

Một quy trình hữu ích khi phân tích thư viện lâu năm, lỗi verifier, dữ liệu class trong hệ thống cũ hoặc công cụ đọc bytecode:

1. **Xác định class cần phân tích và nguồn đáng tin.** Không thực thi binary không rõ nguồn chỉ để xem code; `javap` đọc cấu trúc class file mà không gọi `main`.
2. **Kiểm tra class-file major/minor** bằng `javap -verbose PathToClass.class` hoặc `javap -verbose -classpath legacy.jar package.Name`.
3. **Đọc `Code`** bằng `javap -c -p PathToClass.class`; tìm opcode đúng tên `jsr`, `jsr_w`, `ret`. Đừng tìm chuỗi `ret` vô điều kiện vì nó có thể xuất hiện trong `return` hoặc tên symbol khác.
4. **Lập sơ đồ từng nhánh**: địa chỉ ngay sau mỗi `jsr`; label của subroutine; vị trí `astore` giữ return address; vị trí `ret n`; các exception handlers/bảng ngoại lệ.
5. **Đối chiếu version**: có `jsr`/`ret` mà major ≥ 51 là bất hợp lệ theo JVMS. Nếu major ≤ 50, tiếp tục kiểm tra verifier constraints; xuất hiện opcode không tự chứng minh class hợp lệ.
6. **Đặt vấn đề tương thích đúng nơi**: nếu binary rất cũ vẫn cần chạy, đánh giá JDK/JVM còn hỗ trợ class version, class loader, thư viện và chính sách bảo mật; việc decompile hoặc nâng cấp runtime có thể cần các bước riêng.

Lệnh mẫu (thay tên file/class bằng tên bạn có):

~~~bash
javap -verbose Legacy.class
javap -c -p Legacy.class
javap -c -p -classpath legacy.jar com.example.Legacy
~~~

Trong output `javap`, các offset đầu dòng là **bytecode index (BCI)**, không phải số dòng Java. `jsr 23` nghĩa là chuyển tới bytecode ở BCI 23 (theo cách `javap` hiển thị target), và return address chính là BCI của lệnh kế tiếp sau `jsr`. `ret 2` nghĩa là dùng **local variable slot 2**, không phải “return tới BCI 2”.

Nếu thư viện phân tích bytecode hoặc instrumenter không hiểu `returnAddress` và subroutine legacy, nó có thể dựng control-flow graph sai, nhầm `ret` là method return hoặc xử lý sai kiểu của local slot. Vậy nên biết nhận diện kiểu này giúp **đọc, bảo trì, chuyển đổi và kiểm tra class file cũ**, ngay cả khi không tự viết bytecode cổ.

### Lỗi thường gặp khi đọc và chuyển đổi bytecode

| Lỗi hiểu | Điều chỉnh |
| --- | --- |
| `returnAddress` là con trỏ object hoặc `reference` | Nó là một JVM primitive riêng chỉ dùng cho legacy subroutine flow |
| `ret n` trả giá trị ở local `n` cho caller của method | Nó **nhảy về BCI** chứa trong `local[n]` |
| `jsr` tương tự `invokestatic` | `jsr` vào subroutine trong **cùng method**, không phải gọi Java method khác |
| `astore` chỉ cất Java object reference | Trong ngữ cảnh legacy nó cũng có thể cất `returnAddress` |
| `aload` đọc lại được return address | **Không**: JVMS cố ý không cho `aload` load giá trị này |
| Có `finally` thì bytecode luôn có `jsr` | Compiler Java hiện đại dùng cách khác; major ≥51 cấm ba opcode này |
| Class cũ major ≤50 đương nhiên chạy trên mọi JVM mới | Còn phụ thuộc mức hỗ trợ class version và nhiều ràng buộc runtime khác |
| Không thấy `jsr` trong `javap` nghĩa là `finally` không chạy | Hãy kiểm tra các nhánh control flow và exception table, không suy ra từ opcode legacy |

## 8. Tự kiểm tra kiến thức

**Câu 1.** `returnAddress` có thể được khai báo thành biến Java và in bằng `System.out.println` không?  
**Đáp án:** Không. Đây là kiểu nguyên thủy JVM dành cho luồng điều khiển legacy; không có kiểu source Java tương ứng.

**Câu 2.** `jsr` đẩy lên operand stack giá trị nào?  
**Đáp án:** Một `returnAddress` trỏ tới lệnh **ngay sau** chính lệnh `jsr`. VM sau đó nhảy tới subroutine target.

**Câu 3.** Trong bytecode mẫu, tại sao phải dùng `astore_2` và `ret 2` thay vì `aload_2`?  
**Đáp án:** `astore_2` hợp lệ để lưu return address vào `local[2]`; `aload_2` không được phép load giá trị kiểu này. `ret 2` đọc trực tiếp slot và cập nhật PC.

**Câu 4.** So sánh `ret` với `ireturn`?  
**Đáp án:** `ret` quay lại một BCI **bên trong cùng method** sau `jsr`; `ireturn` kết thúc method hiện tại và trả giá trị `int` cho method caller.

**Câu 5.** File major 52 (Java 8) có được đặt `jsr` vào Code attribute không?  
**Đáp án:** Không, vì major **≥ 51**. Quy tắc không phụ thuộc bạn cố chạy trên HotSpot phiên bản nào.

**Câu 6.** Vì sao vẫn học `returnAddress` nếu Java 17+ không sinh `jsr`?  
**Đáp án:** Để đọc class file cũ, kiểm tra verifier/bytecode, hiểu sự tiến hóa cách biên dịch `finally`, xử lý control-flow graph và đánh giá các công cụ phân tích hoặc chuyển đổi class legacy.

## 9. Nguồn chính thức để đối chiếu

- [JVMS Java SE 25 — §2.3.3 returnAddress Type and Values](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.3.3): định nghĩa loại giá trị, quan hệ với các kiểu nguồn Java.
- [JVMS Java SE 25 — §6.5 Instruction Set](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-6.html): tra cứu `jsr`, `jsr_w`, `astore`, `aload`, `ret` và `return`.
- [JVMS Java SE 25 — §4.9.1 Static Constraints](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.9.1): cấm `jsr`, `jsr_w`, `ret` khi major ≥51; quy tắc xác minh.
- [JVMS Java SE 25 — §4.10.2.5 Exceptions and finally](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.10.2.5): mô tả cơ chế `finally` dùng subroutine trong class file ≤50.
- [JVMS Java SE 25 — §3.13 Compiling finally](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-3.html#jvms-3.13): ví dụ lịch sử với nhánh thường, exception, `jsr` và `ret`.
- [Java SE 7 Compatibility — class major 51](https://www.oracle.com/java/technologies/compatibility.html): liên hệ class file version 51 với Java 7.

**Tóm lại về mặt kỹ thuật:** `returnAddress` là dấu mốc bytecode được `jsr/jsr_w` tạo ra và `ret` tiêu thụ qua local variable, từng dùng để chia sẻ logic `finally` trong cùng phương thức. Từ **class-file major 51 (Java 7)**, ba opcode này bị cấm ở `Code`, nhưng đặc tả vẫn giải thích chúng để JVM/tooling có thể hiểu di sản class file cũ.