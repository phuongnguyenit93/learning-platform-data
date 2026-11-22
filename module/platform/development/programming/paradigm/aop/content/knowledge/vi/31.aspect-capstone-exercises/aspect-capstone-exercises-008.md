# Bài tập tổng hợp: Minh họa pointcut theo luồng điều khiển hoặc mở rộng cấu trúc kiểu

## 1. Mục tiêu của bài

Trong lập trình hướng khía cạnh (**Aspect-Oriented Programming – AOP**), không phải mọi quy tắc xuyên suốt đều chọn được chỉ bằng tên lớp hoặc chữ ký phương thức. Có tình huống yêu cầu **cùng một phương thức nhưng chỉ được áp dụng advice khi nó chạy trong một luồng điều khiển nhất định**. Cũng có yêu cầu mở rộng hợp đồng của một kiểu đang tồn tại mà không trực tiếp sửa tệp nguồn của kiểu ấy.

Bài tập này khám phá hai khả năng khác nhau:

1. **Pointcut theo luồng điều khiển** (*control-flow pointcut*): minh họa `cflow` và `cflowbelow`, kết hợp điều kiện theo call stack động với pointcut tĩnh `execution`.
2. **Mở rộng cấu trúc kiểu** (*inter-type declaration, ITD*): dùng một aspect khai báo thêm method và quan hệ implements interface cho lớp khác, sau đó chứng minh classfile sau weaving có thay đổi tương ứng.

Cần phân biệt ngay: **`cflow` là một pointcut động**, còn **ITD là khai báo thay đổi cấu trúc kiểu tại thời điểm weaving**, không phải một loại pointcut khác. Hai kỹ thuật này có thể cùng xuất hiện trong một hệ thống AOP nhưng giải quyết hai yêu cầu riêng.

Ví dụ sử dụng **Java 17+ và trình biên dịch/weaver AspectJ độc lập** để minh họa khả năng AOP cơ bản và nâng cao. Một cơ chế AOP khác có thể không hỗ trợ `cflow`, việc thêm member hay `declare parents`. Vì vậy hãy phân biệt giữa **ý tưởng thiết kế AOP** và **cú pháp/capability cụ thể của weaver**.

Sau bài học, bạn phải giải thích được tại sao advice được thực thi ở lời gọi nội bộ nhưng không được thực thi ở lời gọi độc lập; tại sao `Invoice` có thể cung cấp method và interface mới trong artifact đã weave; và cách viết test phát hiện các lỗi match quá rộng, thiếu weaving hoặc chạy nhầm bytecode.

## 2. Tình huống nghiệp vụ và tiêu chí nghiệm thu

Ứng dụng đơn giản có hai yêu cầu:

**Yêu cầu A – quan sát tồn kho trong quá trình checkout.** Method `Inventory.read(String)` có thể chạy ở nhiều nơi. Chỉ khi nó được gọi trong đường thực thi đồng bộ đang nằm bên trong `OrderService.checkout()`, advice mới in một dòng `FLOW: inventory read inside checkout`. Khi `Inventory.read` được gọi trực tiếp bên ngoài checkout, **không** in dòng đó. Không thay đổi kết quả và thứ tự nghiệp vụ.

**Yêu cầu B – tăng khả năng cho lớp hóa đơn.** Lớp `Invoice` ban đầu chỉ có dữ liệu và phương thức `amount()`; không khai báo `label()` và không implements `Billable` trong mã nguồn. Một aspect khác phải:

- Khai báo `Invoice implements Billable`.
- Bổ sung method `String label()` trả về chuỗi `INVOICE:<amount>`.
- Cho phép mã ứng dụng gọi `invoice.label()` và kiểm tra `invoice instanceof Billable` sau khi compile/weave thành công.

### Ma trận kết quả dự kiến

| Thao tác | Điểm được chọn / thay đổi | Kết quả bắt buộc |
|---|---|---|
| `OrderService.checkout()` gọi `Inventory.read("inside")` | `execution(Inventory.read)` nằm trong `cflow(checkout)` | Một dòng `FLOW: ...` trước `INVENTORY:inside` |
| `new Inventory().read("outside")` | Cùng method nhưng **không** nằm trong checkout | Chỉ `INVENTORY:outside`, không có `FLOW` |
| Tạo `new Invoice(42)` | Class được weave thêm interface và method | Khởi tạo và đọc amount bình thường |
| `invoice.label()` | Method được khai báo qua ITD | In `INVOICE:42` |
| `invoice instanceof Billable` | Quan hệ type được thêm qua `declare parents` | `true` |
| Chạy Java class chưa weave | Thiếu thay đổi ở bytecode/kiểu | Không thỏa toàn bộ hợp đồng bài tập |

Điểm quan trọng nhất của bài là **kiểm thử trường hợp không được chọn**, chứ không chỉ xem có thêm được một dòng advice hay không.

## 3. Kiến thức nền: static pointcut, dynamic pointcut và ITD

### 3.1. Phần nào xác định được khi weave?

`execution(void demo.flow.Inventory.read(String))` biểu thị method execution với chữ ký cụ thể. Weaver có thể tìm các method execution join point tương ứng từ mã đầu vào. Đây là phần **lọc theo cấu trúc tĩnh**.

Ngược lại, cùng method `Inventory.read` có thể được gọi trong hoặc ngoài checkout. Điều kiện đó phụ thuộc **đường thực thi hiện thời**. `cflow(execution(void demo.flow.OrderService.checkout()))` chỉ đúng khi chương trình đang ở trong luồng điều khiển động bắt nguồn từ execution join point được mô tả. Weaver có thể chuẩn bị mã theo dõi phạm vi, nhưng việc một lời gọi thuộc phạm vi hay không phải xét tại runtime.

Ví dụ:

```text
main
 ├─ OrderService.checkout()          <-- bắt đầu phạm vi cflow
 │   ├─ validate()
 │   └─ Inventory.read("inside")    <-- đúng điều kiện cflow
 │       └─ return
 │   └─ return                      <-- kết thúc phạm vi
 └─ Inventory.read("outside")        <-- không thuộc cflow
```

**Điều kiện đồng thời:** để advice chạy, method phải vừa khớp `execution(Inventory.read)` **vừa** nằm trong `cflow(checkout)`. Chỉ dùng `cflow` mà không giới hạn execution có thể khiến advice chạy trên rất nhiều join point thuộc toàn bộ nhánh điều khiển.

### 3.2. Khác biệt `cflow` và `cflowbelow`

Trong ngữ nghĩa AspectJ:

- `cflow(P)` chọn các join point trong luồng điều khiển động bắt nguồn từ join point khớp `P`, **bao gồm chính join point bắt đầu**.
- `cflowbelow(P)` chọn các join point **nằm dưới** join point bắt đầu đó, **không bao gồm join point bắt đầu**.

Nếu `P` là `execution(void OrderService.checkout())`, thì advice gắn lên chính execution `checkout()` sẽ thấy khác biệt giữa `cflow(P)` và `cflowbelow(P)`. Tuy nhiên, khi advice đã giới hạn ở execution `Inventory.read(String)` được gọi **bên trong** checkout, cả hai cách đều có thể chọn cùng lời gọi nội bộ đó trong ví dụ thông thường.

Nói “`cflowbelow` loại toàn bộ lời gọi trực tiếp bên trong method gốc” là sai: nó chỉ loại **join point bắt đầu `P`**, không loại các join point thực thi bên dưới.

### 3.3. ITD là gì?

Inter-type declaration (còn được gọi là *introduction* trong một số mô hình AOP) cho phép một aspect tuyên bố member hoặc quan hệ kiểu cho một lớp khác. Với AspectJ, các ví dụ điển hình là:

- Khai báo thêm method hoặc field cho type khác.
- Dùng `declare parents` để khai báo type thực hiện một interface hay tham gia quan hệ kế thừa được hỗ trợ.

Sau compile-time weaving, bytecode của lớp bị tác động có thể chứa các member/interface được bổ sung. Điều này khác về bản chất với proxy: **ITD thay đổi cấu trúc classfile mà JVM nhìn thấy**, còn interceptor tại runtime có thể chỉ điều hướng một lời gọi mà không bổ sung member thật vào class gốc.

Không phải thay đổi cấu trúc nào cũng hợp lệ. Các quy tắc access, xung đột method đã tồn tại, class/interface hierarchy, hạn chế từ weaver và tính tương thích nhị phân đều phải được xem xét.

## 4. Thiết kế dự án Java 17+

Một dự án minh họa cả hai kỹ thuật, giữ riêng mỗi aspect để dễ quan sát:

```text
aop-control-type-lab/
├── src/
│   └── demo/
│       ├── Main.java
│       ├── flow/
│       │   ├── Inventory.java
│       │   └── OrderService.java
│       ├── structure/
│       │   ├── Billable.java
│       │   └── Invoice.java
│       └── aspect/
│           ├── FlowTrace.aj
│           └── InvoiceExtension.aj
└── tools/
    ├── aspectjtools-1.9.24.jar
    └── aspectjrt-1.9.24.jar
```

Các tệp Java được viết bằng cú pháp Java 17; tệp `.aj` chứa cú pháp AspectJ và được biên dịch bằng `ajc`, **không phải bởi `javac` thuần**. Khi `Main.java` gọi member chỉ được khai báo bằng ITD, cần đưa cả `Main.java`, `Invoice.java` và aspect liên quan vào quy trình compile/weave có nhận thức về ITD.

## 5. Phần A: chọn join point bằng luồng điều khiển

### 5.1. Mã nghiệp vụ tồn kho

Tạo `src/demo/flow/Inventory.java`:

```java
package demo.flow;

public final class Inventory {
    public void read(String sku) {
        System.out.println("INVENTORY:" + sku);
    }
}
```

Lớp này **không biết** điều kiện checkout. Dù được gọi từ đâu, nó luôn in kết quả nghiệp vụ giống nhau. Mục tiêu AOP là bổ sung dòng tracing đúng ngữ cảnh.

### 5.2. Mã nghiệp vụ checkout

Tạo `src/demo/flow/OrderService.java`:

```java
package demo.flow;

public final class OrderService {
    private final Inventory inventory = new Inventory();

    public void checkout() {
        System.out.println("CHECKOUT START");
        inventory.read("inside");
        System.out.println("CHECKOUT END");
    }
}
```

Một lần `checkout()` thực thi, gọi `Inventory.read` trong thời gian checkout chưa trả về. Đây là join point mà trace cần nhận diện.

### 5.3. Aspect theo `cflow`

Tạo `src/demo/aspect/FlowTrace.aj`:

```java
package demo.aspect;

public aspect FlowTrace {
    pointcut duringCheckout():
        cflow(execution(void demo.flow.OrderService.checkout()));

    before():
        execution(void demo.flow.Inventory.read(java.lang.String))
        && duringCheckout() {
        System.out.println("FLOW: inventory read inside checkout");
    }
}
```

Phân tích:

1. `execution(void demo.flow.OrderService.checkout())` xác định **gốc luồng điều khiển**.
2. `cflow(...)` chọn ngữ cảnh runtime bắt nguồn từ execution đó, bao gồm các method được gọi lồng bên dưới trên đường thực thi hiện hành.
3. `execution(void demo.flow.Inventory.read(java.lang.String))` giới hạn đối tượng được advice tới method tồn kho.
4. `&&` yêu cầu **cả hai** điều kiện cùng đúng.
5. `before()` ghi dòng trace trước khi thân `Inventory.read` chạy.

Kết quả: phương thức tồn kho vẫn được gọi bình thường ở cả hai nơi, nhưng **chỉ lời gọi trong checkout** được thêm trace.

Không viết pointcut như `execution(* *(..)) && cflow(...)` trong bài này: biểu thức đó có thể match cả helper, getter hoặc các method không thuộc ý định theo dõi.

### 5.4. Nên thay `cflow` bằng `cflowbelow` khi nào?

Khi cần chọn **mọi join point ở dưới** một execution gốc mà **loại chính execution gốc**, có thể viết:

```java
// Một biểu thức pointcut minh họa trong aspect:
pointcut nestedCheckoutFlow():
    cflowbelow(execution(void demo.flow.OrderService.checkout()));
```

Đây là **mảnh pointcut**, không phải chương trình Java chạy độc lập. Nếu kết hợp với `execution(Inventory.read(String))` của ví dụ, kết quả gọi bên trong checkout vẫn tương tự. Nếu advice nhắm chính `checkout`, hai lựa chọn có thể cho tập join point khác. Hãy kiểm tra ngữ nghĩa trên các đường gọi lồng nhau và lời gọi đệ quy trước khi chọn.

## 6. Phần B: bổ sung hợp đồng cấu trúc kiểu bằng ITD

### 6.1. Interface cần mở rộng

Tạo `src/demo/structure/Billable.java`:

```java
package demo.structure;

public interface Billable {
}
```

Interface ở đây được giữ là **marker interface** để tập trung vào việc thay đổi type relationship. Trong ứng dụng thật, interface có thể định nghĩa các method khác; khi đó lớp sau weaving phải thỏa mọi method bắt buộc hoặc dựa trên các cơ chế hiện thực hợp lệ.

### 6.2. Lớp gốc không biết aspect

Tạo `src/demo/structure/Invoice.java`:

```java
package demo.structure;

public final class Invoice {
    private final int amount;

    public Invoice(int amount) {
        this.amount = amount;
    }

    public int amount() {
        return amount;
    }
}
```

Quan sát trực tiếp source: `Invoice` **không có method `label()`** và **không implements `Billable`**. Điều này là có chủ đích để kiểm chứng phép mở rộng cấu trúc kiểu do aspect thực hiện.

### 6.3. Aspect khai báo thêm interface và method

Tạo `src/demo/aspect/InvoiceExtension.aj`:

```java
package demo.aspect;

public aspect InvoiceExtension {
    declare parents:
        demo.structure.Invoice implements demo.structure.Billable;

    public String demo.structure.Invoice.label() {
        return "INVOICE:" + amount();
    }
}
```

Giải thích:

- `declare parents` tuyên bố quan hệ `Invoice implements Billable` ở thời điểm weaving.
- Cú pháp `public String demo.structure.Invoice.label()` là **inter-type method declaration**: method mới có tên `label()` được khai báo cho kiểu `Invoice`, dù source `Invoice.java` không chứa method này.
- Thân ITD gọi method `amount()` vốn đã là `public`; không cần truy cập trực tiếp vào field `private amount`.
- Hai khai báo làm thay đổi **hợp đồng kiểu** khi compile/weave; chúng không phải advice `before` hoặc `after` và không dựa vào việc có một lời gọi đang nằm trong `cflow`.

Khi chọn cấu trúc kiểu để mở rộng, cần quan tâm API compatibility, xung đột tên member và quan hệ kế thừa. Ví dụ, nếu sau này tác giả `Invoice` tự thêm `label()` với chữ ký trùng nhau, cần giải quyết theo quy tắc của compiler/weaver; không giả định hai method sẽ được giữ độc lập.

### 6.4. Hệ quả cho người dùng class

Với artifact **đã weave**, code có thể gọi `invoice.label()` và dùng `instanceof Billable`. Nhưng nếu một module khác chỉ biên dịch dựa trên bản `Invoice.class` **chưa weave**, compiler Java thuần không thể suy ra ITD từ mã nguồn `Invoice.java`. Do đó, nếu ITD trở thành API công khai, cần tổ chức build để các module sử dụng được **woven classes** hay các signature metadata thích hợp, đồng thời đảm bảo JVM runtime load chính artifact tương ứng.

Đây là khác biệt lớn với advice thuần hành vi: một ITD public có thể ảnh hưởng trực tiếp tới **tính tương thích biên dịch và nhị phân** của consumer.

## 7. Chương trình chính và stdout kỳ vọng

Tạo `src/demo/Main.java`:

```java
package demo;

import demo.flow.Inventory;
import demo.flow.OrderService;
import demo.structure.Billable;
import demo.structure.Invoice;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        OrderService service = new OrderService();
        service.checkout();

        new Inventory().read("outside");

        Invoice invoice = new Invoice(42);
        System.out.println(invoice.label());
        System.out.println("BILLABLE:" + (invoice instanceof Billable));
    }
}
```

Khi compile/weave cùng hai aspect thành công, đầu ra **stdout của ứng dụng** theo thứ tự:

```text
CHECKOUT START
FLOW: inventory read inside checkout
INVENTORY:inside
CHECKOUT END
INVENTORY:outside
INVOICE:42
BILLABLE:true
```

**Giải thích từng phần:**

1. `CHECKOUT START` xuất hiện trước khi checkout gọi Inventory.
2. `FLOW: ...` xuất hiện **một lần** vì `Inventory.read("inside")` đang ở trong dynamic control flow của checkout.
3. `INVENTORY:inside` là nội dung nghiệp vụ gốc; `CHECKOUT END` cho thấy checkout không bị ngắt.
4. `INVENTORY:outside` xuất hiện mà **không có** dòng `FLOW: ...` thứ hai, dù thực thi **cùng method `Inventory.read`**.
5. `INVOICE:42` chứng minh method `label()` do ITD thêm đã được gọi.
6. `BILLABLE:true` chứng minh quan hệ interface được đưa vào type khi weaving.

Hai dòng cuối **không có nghĩa** `Invoice` được proxy bao quanh hoặc call stack đang thuộc checkout; đó là kết quả của biến đổi cấu trúc lớp.

## 8. Biên dịch/weave và chạy với Java 17+

Ví dụ lệnh dùng terminal **POSIX/bash** trong thư mục `aop-control-type-lab`. Cần JDK 17+ và AspectJ compiler hỗ trợ đích Java 17. Ví dụ này chọn **AspectJ 1.9.24** và dùng cùng phiên bản cho compiler và runtime.

### 8.1. Chuẩn bị công cụ

```bash
mkdir -p tools build/woven

curl -fLsS \
  https://repo.maven.apache.org/maven2/org/aspectj/aspectjtools/1.9.24/aspectjtools-1.9.24.jar \
  -o tools/aspectjtools-1.9.24.jar

curl -fLsS \
  https://repo.maven.apache.org/maven2/org/aspectj/aspectjrt/1.9.24/aspectjrt-1.9.24.jar \
  -o tools/aspectjrt-1.9.24.jar
```

**Lưu ý build sạch:** các lệnh bên dưới giả định `build/woven` chưa chứa bytecode từ lần build cũ. Trong pipeline, cần dọn output **của chính lab** trước lần compile độc lập để tránh class cũ đi vào kết quả; không cần đụng đến dự án khác.

### 8.2. Compile-time weaving một lượt

```bash
java -cp tools/aspectjtools-1.9.24.jar \
  org.aspectj.tools.ajc.Main \
  -17 -encoding UTF-8 \
  -classpath tools/aspectjrt-1.9.24.jar \
  -showWeaveInfo \
  -d build/woven \
  src/demo/flow/Inventory.java \
  src/demo/flow/OrderService.java \
  src/demo/structure/Billable.java \
  src/demo/structure/Invoice.java \
  src/demo/aspect/FlowTrace.aj \
  src/demo/aspect/InvoiceExtension.aj \
  src/demo/Main.java
```

Lệnh `java -cp ... org.aspectj.tools.ajc.Main` chạy AspectJ compiler. `-17` chọn target/source Java 17, `-d` chỉ định output chứa **woven class**, `-showWeaveInfo` yêu cầu thông tin các join point và khai báo áp dụng. Định dạng và số dòng weave report có thể khác theo compiler/version, vì vậy không dựa vào một bản ghi log viết cứng để kết luận.

Compiler cần nhìn thấy cả khai báo `InvoiceExtension.aj` khi biên dịch `Main.java` sử dụng `Invoice.label()`. Chạy riêng `javac src/demo/Main.java` trên source chưa weave là một phép thử **không tương đương** và dự kiến không thể phân giải method mới.

### 8.3. Chạy chương trình

```bash
java -cp "build/woven:tools/aspectjrt-1.9.24.jar" demo.Main
```

Stdout phải khớp mục 7. Trên Windows, thay dấu `:` phân cách classpath bằng dấu `;` theo quy tắc của JVM trên nền tảng đó.

### 8.4. Đóng gói và kiểm tra chính artifact đã dệt

```bash
jar --create \
  --file build/control-type-woven.jar \
  -C build/woven .

jar --list --file build/control-type-woven.jar

javap -classpath build/control-type-woven.jar \
  -p demo.structure.Invoice
```

Các kiểm tra cần thực hiện:

- JAR có `demo/flow/Inventory.class`, `demo/flow/OrderService.class`, `demo/structure/Invoice.class`, `demo/structure/Billable.class`, `demo/Main.class` và class của aspect cần thiết.
- `javap -p` trên `Invoice` sau weaving cho thấy method `label()` và quan hệ implements `Billable` phù hợp với kết quả biên dịch (cách in signature có thể khác).
- Kiểm tra bytecode `Inventory.read` cũng có thể xác định thêm logic advice đã được weave; với pointcut động, compiler có thể sinh helper/test runtime. Tên helper là chi tiết thực thi, không nên dùng làm hợp đồng dài hạn.
- Cần chạy lại **chính JAR cuối** để phát hiện trường hợp package nhầm class chưa weave:

```bash
java -cp "build/control-type-woven.jar:tools/aspectjrt-1.9.24.jar" \
  demo.Main
```

Output phải giống mục 7. JAR ví dụ **không nhúng** thư viện `aspectjrt`: khi triển khai phải phân phối dependency phù hợp hoặc xây package tự chứa đúng cách.

## 9. Kiểm thử dương và âm cho `cflow`

### 9.1. Cặp kiểm thử quan trọng nhất

- **Positive case:** `Inventory.read("inside")` chạy trong checkout → có một dòng `FLOW`.
- **Negative case:** `Inventory.read("outside")` chạy ngoài checkout → không có dòng `FLOW`.

Nếu chỉ kiểm tra “chương trình có in FLOW” thì pointcut `execution(void Inventory.read(String))` thiếu `cflow` cũng có thể pass. Phải kiểm tra **lượt nào** bị chặn, không chỉ tổng số ít nhất một.

Đoạn shell kiểm thử output của bản chạy độc lập:

```bash
actual=$(java -cp \
  "build/control-type-woven.jar:tools/aspectjrt-1.9.24.jar" \
  demo.Main)

expected=$(printf '%s\n' \
  'CHECKOUT START' \
  'FLOW: inventory read inside checkout' \
  'INVENTORY:inside' \
  'CHECKOUT END' \
  'INVENTORY:outside' \
  'INVOICE:42' \
  'BILLABLE:true')

test "$actual" = "$expected"
```

Lệnh `test` trả mã khác `0` nếu mất advice, log thêm ở lời gọi ngoài checkout, hoặc phần ITD không tạo đúng output. Đây là test cho **chương trình đơn luồng có stdout xác định**. Trong production, log của nhiều thread có thể xen kẽ: nên assert dựa trên event/correlation ID theo request thay vì giả định một thứ tự log global.

### 9.2. Các biến thể mở rộng phạm vi

**Biến thể 1 – checkout gọi qua helper.** Thêm helper đồng bộ được gọi từ checkout, rồi helper gọi `Inventory.read`. Method read vẫn thuộc dynamic control flow của checkout và cần có trace. Điều này chứng minh `cflow` không chỉ match caller trực tiếp.

**Biến thể 2 – chuyển sang thread khác.** Nếu checkout khởi tạo công việc bất đồng bộ chạy sau/ở một thread khác, không tự mặc định dynamic control flow của checkout sẽ được truyền qua thread đó. Trong AspectJ thông thường, `cflow` dựa trên luồng thực thi động của join point hiện tại và không có chức năng tự mang business context qua mọi ranh giới bất đồng bộ. Muốn trace xuyên thread/task, cần cơ chế truyền context rõ ràng được thiết kế và test riêng.

**Biến thể 3 – gọi lồng/đệ quy.** Khi checkout được gọi lồng hoặc đệ quy, phạm vi `cflow` có thể bao gồm nhiều mức hoạt động; giải thích xem một lần read có thuộc các phạm vi đang hoạt động hay không. Đừng giả định một lời gọi read luôn chỉ có một gốc checkout.

**Biến thể 4 – thêm điều kiện động.** Nếu chỉ trace một SKU cụ thể, kết hợp context/argument binding theo capability công cụ. Cần đánh giá thêm chi phí kiểm tra runtime và chú ý `null`, kiểu runtime của đối số.

### 9.3. Chi phí runtime của `cflow`

Một điều kiện chữ ký/type thuần thường có thể lọc nhiều join point khi weave. `cflow` phải duy trì/kiểm tra trạng thái phạm vi luồng điều khiển khi chương trình chạy; mã phụ trợ và chi phí cụ thể phụ thuộc weaver. Trong đường gọi cực nóng, trace mọi lần read có thể gây allocation, log I/O và latency đáng kể. Đo với workload đại diện và giới hạn pointcut tĩnh càng rõ càng tốt; không đưa `cflow` lên tất cả execution trong toàn ứng dụng nếu không cần.

## 10. Kiểm thử cấu trúc kiểu sau ITD

### 10.1. Tại sao test `instanceof` là cần thiết?

Nếu chỉ kiểm tra chuỗi `INVOICE:42`, về mặt thiết kế có thể đạt kết quả đó bằng một utility method hoặc formatter ngoài lớp, chứ chưa chứng minh `Invoice` thực sự được mở rộng. Bài này cần test **hai dấu hiệu độc lập**:

1. Một instance `Invoice` gọi được method `label()` trực tiếp sau compile/weave.
2. Instance đó thỏa quan hệ `instanceof Billable` vì `declare parents` đã được áp dụng.

`javap` bổ sung chứng cứ rằng thay đổi hiện diện trong classfile, nhưng hành vi runtime vẫn cần kiểm chứng.

### 10.2. Các kiểm tra phản chứng

Thử nghiệm mang tính học tập, thực hiện trên các build riêng:

- **Bỏ ITD method `label()`:** source `Main.java` đang gọi method này phải không còn build được nếu không có thay đổi tương đương khác; điều này xác nhận consumer phụ thuộc vào cấu trúc do weaving bổ sung.
- **Bỏ `declare parents`:** method `label()` có thể vẫn tồn tại nhưng quan hệ implements `Billable` không còn đáp ứng hợp đồng; compile của đoạn `instanceof` có thể thay đổi tùy type checker và cách tổ chức build, vì vậy kiểm tra trên class đã weave thay vì dự đoán máy móc một lỗi compiler cụ thể.
- **Compile consumer trên class chưa weave:** Java compiler sẽ không tự nhận biết các member chỉ xuất hiện trong `.aj`. Cần đúng output và thứ tự build.
- **Thêm method trùng chữ ký vào source `Invoice`:** yêu cầu xử lý xung đột/đặc tả weaver; không được tự động “merge” hai cách hiện thực.

### 10.3. Khả năng bảo trì

ITD có thể giúp bổ sung một concern về hợp đồng kiểu mà không phải sửa nhiều lớp nguồn. Tuy nhiên, nó làm API được nhìn thấy ở runtime **khác** với API thuần đọc từ source type ban đầu. Vì vậy:

- Ghi tài liệu cho public member được đưa vào qua aspect.
- Đảm bảo IDE, compiler, test và consumer dùng đúng build metadata/classpath.
- Không mở rộng cấu trúc lớp của bên thứ ba một cách thiếu kiểm soát.
- Kiểm tra binary compatibility và xung đột tên qua các lần nâng phiên bản dependency.
- Tránh dùng ITD để che giấu quan hệ kiểu quá quan trọng đến mức người đọc code không tìm ra nguyên nhân.

## 11. Phân biệt `cflow` với các khái niệm dễ nhầm

| Khái niệm | Điều kiện chính | Sai lầm thường gặp |
|---|---|---|
| `execution(P)` | Method/constructor execution hoặc loại join point tương ứng khớp signature/type | Tưởng rằng nó tự biết caller hoặc business request hiện tại |
| `call(P)` | Call site phù hợp | Nhầm với execution trên target khi caller không được weave |
| `within(TypePattern)` | Lexical type chứa join point | Nghĩ rằng package/type đồng nghĩa với call stack nghiệp vụ |
| `withincode(Signature)` | Lexical code chứa join point | Nhầm với tất cả lời gọi lồng nhau lúc runtime |
| `cflow(P)` | Dynamic control flow bắt nguồn từ P, gồm join point gốc | Cho rằng chỉ xét caller trực tiếp |
| `cflowbelow(P)` | Dynamic control flow **dưới** P, trừ gốc | Cho rằng loại mọi join point bên trong method gốc |
| `args(...)` | Điều kiện/binding theo đối số runtime khi được hỗ trợ | Đồng nhất với signature tham số khai báo |
| **ITD** | Thêm member/hợp đồng kiểu ở weaving | Gọi nó là một dynamic pointcut |

Đặc biệt, `within(OrderService)` có thể chọn các join point nằm **trong mã của OrderService**. Nó không tự chọn một `Inventory.read` được thực thi trong lớp `Inventory` chỉ vì method đó được gọi từ `OrderService.checkout`. Chính `cflow` diễn đạt ngữ cảnh call stack mà ví dụ yêu cầu.

## 12. Những lỗi thường gặp trong bài tập

**Lỗi 1 – bỏ điều kiện execution của Inventory.** Viết advice trên `cflow(checkout)` đơn thuần có thể áp dụng cho hàng loạt join point trong đường checkout. **Sửa:** kết hợp `execution(Inventory.read) && cflow(checkout)`.

**Lỗi 2 – dùng `within(OrderService)` thay `cflow(checkout)`.** `within` là điều kiện lexical chứ không mô tả toàn bộ call stack. **Sửa:** xác định mục tiêu theo ngữ cảnh runtime và dùng designator phù hợp.

**Lỗi 3 – tin rằng `cflowbelow` không match lời gọi read ngay trong checkout.** `cflowbelow` chỉ loại join point gốc, không loại các execution nằm dưới. **Sửa:** vẽ cây lời gọi và xác định gốc pointcut.

**Lỗi 4 – dùng lời gọi bất đồng bộ rồi đợi `cflow` tự theo context.** Một task/thread khác không nhất thiết nằm trong dynamic control flow của thread gốc. **Sửa:** thiết kế context propagation riêng và test thời điểm task thực thi.

**Lỗi 5 – cho rằng ITD chỉ là phương thức tiện ích.** Utility bên ngoài không thêm thật method/interface vào `Invoice`. **Sửa:** kiểm tra `Invoice.label()` và `instanceof Billable` trên woven class.

**Lỗi 6 – biên dịch `Main.java` bằng `javac` với class gốc và mong thấy `label()`.** Compiler Java thuần chỉ thấy API gốc. **Sửa:** dùng AspectJ-aware compilation hoặc đưa woven artifact phù hợp lên compile classpath.

**Lỗi 7 – đóng gói nhầm class chưa weave.** Build log có thể đúng nhưng runtime không có advice/ITD vì chạy JAR plain. **Sửa:** dùng thư mục đầu ra weaving cho packaging và test chính JAR đó.

**Lỗi 8 – bỏ dependency runtime.** Woven bytecode có thể cần lớp trong `aspectjrt` hoặc helper tương ứng. **Sửa:** phân phối và kiểm tra dependency bằng lệnh chạy thực.

**Lỗi 9 – không kiểm tra trường hợp bên ngoài checkout.** Advice có thể match quá rộng nhưng test vẫn pass vì chỉ thấy một dòng FLOW. **Sửa:** thêm negative case phải chắc chắn không có trace.

**Lỗi 10 – kỳ vọng weaving tái định nghĩa mọi quan hệ kiểu trong JVM đang chạy.** Structural introduction chịu giới hạn compiler/weaver và thời điểm class được định nghĩa. **Sửa:** chọn chiến lược weaving đáp ứng khả năng cấu trúc cần thiết và kiểm tra bytecode/runtime.

## 13. Bài tập mở rộng

### Bài A – dùng `cflowbelow` và giải thích khác biệt

Viết pointcut `insideCheckoutBelow()` dùng `cflowbelow(execution(void OrderService.checkout()))`. Thực hiện hai phép quan sát:

- Advice cho **chính execution `checkout`**: điều gì khác giữa `cflow` và `cflowbelow`?
- Advice cho **execution `Inventory.read` bên dưới checkout**: điều gì giữ nguyên?

Lời giải đạt yêu cầu khi học viên giải thích đúng phạm vi join point gốc và lớp con, không chỉ nêu một giá trị boolean.

### Bài B – thêm một helper lồng nhau

Đưa `Inventory.read("inside")` vào `OrderHelper.load` do `checkout` gọi. `FlowTrace` không cần biết tên helper nhưng vẫn phải chọn read khi thuộc checkout. Thêm negative test gọi `OrderHelper.load` từ bên ngoài checkout để xác nhận không bị trace. Tình huống này chỉ ra ưu thế của **ngữ cảnh động** so với match theo tên caller cụ thể.

### Bài C – thêm interface có phương thức

Đổi `Billable` từ marker thành hợp đồng:

```java
package demo.structure;

public interface Billable {
    String label();
}
```

Giữ ITD method `Invoice.label()` và `declare parents`. Biên dịch lại và kiểm tra một biến `Billable billable = invoice;` có thể gọi `billable.label()` sau weaving. Nếu hợp đồng interface có thêm method chưa được cung cấp, compiler/weaver có thể báo lỗi; học viên phải chứng minh lớp thỏa đầy đủ interface.

### Bài D – kiểm soát thời gian và logging

Thêm advice đo thời lượng trên một join point xác định, dùng phép đo đúng cho benchmark (warmup, nhiều vòng đo, workload đại diện) và không tạo log khối lượng lớn trong vòng lặp nóng. Đo cả phần overhead của cflow và I/O logging; không lấy một phép `System.nanoTime()` duy nhất làm bằng chứng tốc độ.

### Bài E – tổ chức build nhiều module

Module A tạo woven `Invoice.class`; module B gọi `label()`. Thử compile module B lần lượt với **plain JAR** và **woven JAR**. Giải thích sự khác biệt compile-time visibility và runtime classpath. Sau đó xem xét trường hợp tồn tại hai bản `Invoice.class` trên classpath; xác định loader đang dùng bản nào.

## 14. Tiêu chí chấm và checklist

| Hạng mục | Trọng số | Bằng chứng |
|---|---:|---|
| Hiểu `cflow` / `cflowbelow` | 20% | Giải thích call stack và join point gốc chính xác |
| Pointcut chọn đúng | 20% | Trace đúng `read("inside")`, không trace `read("outside")` |
| ITD đúng cấu trúc | 20% | `Invoice.label()` và `instanceof Billable` hoạt động |
| Build/weaving | 15% | JDK 17+, ajc, weave info và artifact cuối có thể chạy |
| Kiểm thử dương/âm | 15% | Có assertion cho cả trường hợp đúng và bị loại |
| Giải thích rủi ro | 10% | Đề cập threading, runtime overhead, classpath, xung đột ITD |

Trước khi hoàn thành, kiểm tra:

- [ ] Phân biệt được **dynamic control flow pointcut** với **static type introduction**.
- [ ] Code `Main` chạy bằng compiler/weaver phù hợp và dùng đúng woven class.
- [ ] `Inventory.read` có một lời gọi trong checkout và một lời gọi ngoài checkout.
- [ ] Dòng `FLOW` chỉ xuất hiện một lần, ở đúng vị trí trước `INVENTORY:inside`.
- [ ] Không in dòng FLOW bổ sung trước `INVENTORY:outside`.
- [ ] Method `label()` không tồn tại trong mã nguồn `Invoice` nhưng tồn tại ở woven artifact.
- [ ] Quan hệ implements `Billable` có thật và kiểm tra runtime cho kết quả `true`.
- [ ] Cả stdout, weave report, disassembly và artifact cuối được xem xét.
- [ ] Không giả định điều kiện cflow tự truyền xuyên mọi thread/task.
- [ ] Đã xem xét ảnh hưởng API compatibility và phụ thuộc khi dùng ITD.

**Kết quả cần ghi nhớ:** `cflow` cho phép mô tả **“một hành vi đang xảy ra trong ngữ cảnh thực thi nào”**; ITD cho phép mô tả **“một kiểu có thêm hợp đồng/member nào sau weaving”**. Chúng kết hợp được với AOP nhưng cần kiểm thử ở những lớp khác nhau: **đường gọi runtime** cho pointcut động và **cấu trúc classfile/API** cho inter-type declaration.