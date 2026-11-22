# Java 7 — MethodHandle: Kết hợp hành vi qua các bộ biến đổi MethodHandles

## 1. Mục tiêu bài học

`java.lang.invoke.MethodHandle` là một tham chiếu có kiểu tới một thao tác có thể được JVM gọi trực tiếp theo chữ ký cụ thể. `MethodHandles` cung cấp các **combinators** để tạo handle mới bằng cách lắp ghép handle cũ: lọc tham số, xử lý giá trị trả về, cố định hoặc hoán đổi tham số, rẽ nhánh, bắt ngoại lệ, tạo loop và dọn dẹp.

Chủ đề cha: **MethodHandle**. Đề bài trực tiếp: **Kết hợp hành vi qua các bộ biến đổi MethodHandles**.

Những API cơ bản của `java.lang.invoke` đã có từ Java 7; một số combinator bổ sung như `countedLoop` và `tryFinally` chỉ xuất hiện từ Java 9. Bài dùng **Java 17+** để học các API còn được hỗ trợ hiện nay; không dùng `sun.misc.Unsafe`, JDK private internals, illegal reflection hoặc các workaround legacy.

Bạn sẽ có thể:
- Xác định chuẩn xác `MethodType` của method gốc và adapter.
- Dùng `MethodHandles.lookup()`, `findStatic` và `findVirtual` theo quyền truy cập.
- Kết hợp `filterArguments` và `filterReturnValue` để tạo pipeline.
- Bind đối số bằng `insertArguments` hoặc `bindTo`; thêm tham số bỏ qua bằng `dropArguments`.
- Đổi, nhân bản và bỏ qua các đối số bằng `permuteArguments`.
- Rẽ nhánh với `guardWithTest`; bắt loại ngoại lệ cụ thể bằng `catchException`.
- Khác nhau giữa `foldArguments`, `collectArguments`, `asCollector` và `asSpreader`.
- Dùng `asType` và `explicitCastArguments`, hiểu điều kiện conversion và overflow.
- Hiểu `invokeExact`, `invoke` và `WrongMethodTypeException`.
- Kết hợp control flow/cleanup bằng `countedLoop` và `tryFinally`.
- Chọn code dễ bảo trì, quản lý thread safety/lookup permissions và kiểm thử đầy đủ.

**Nguyên tắc:** Các combinators tạo **MethodHandle thích nghi mới**, không sửa method/bytecode gốc. Điều kiện kiểu được kiểm soát nghiêm ngặt bởi `MethodType`; hãy kiểm `handle.type()` sau mỗi phép biến đổi.

## 2. MethodType: chữ ký là một phần của hành vi

`MethodType` lưu **kiểu trả về, số lượng và thứ tự các tham số**, không có tên tham số hoặc body. Ví dụ:

```java
MethodType type = MethodType.methodType(
    int.class, int.class, int.class);
MethodHandle add = MethodHandles.lookup().findStatic(
    Calculator.class, "add", type);
```

Đây là **mảnh minh họa**, chưa có class `Calculator`. Nếu `Calculator` khai báo `static int add(int,int)` accessible, handle sẽ có type `(int,int)int`.

```text
MethodType: (String,int)boolean
               |      |     |
              arg0   arg1  return

MethodHandle: type() + target/adaptation + invocation semantics
```

Khi gọi `invokeExact`, cả kiểu đối số **và kiểu trả về do compiler suy ra ở call site** phải giống type. Một return cast thiếu hoặc sai có thể gây `WrongMethodTypeException` dù method target hợp lệ.

### 2.1. Ví dụ phép đại số kiểu

```text
square:                   (int)int
parse:                    (String)int
filterArguments:          (String)int
label:                    (int)String
filterReturnValue:        (String)String
```

Đầu vào bên ngoài đã chuyển từ `int` sang `String` và đầu ra từ `int` sang `String`. Logic tính bình phương không thay đổi.

## 3. Lookup, method gốc và access control

`MethodHandles.lookup()` lấy một `Lookup` với quyền gắn với caller class. Thông dụng:

- `findStatic(Owner.class,name,type)` trả handle đến static method.
- `findVirtual(Owner.class,name,type)` trả handle có **receiver đứng đầu** khi invoke.
- `findConstructor(Owner.class,methodType(void.class,...))` dùng cho constructor.
- `findGetter`/`findSetter` cho field access khi hợp lệ.
- `publicLookup()` chỉ cung cấp quyền truy cập public thích hợp.

Không có quyền đọc mọi method private qua `lookup()`. `privateLookupIn` (Java 9+) cũng phải tuân module opens/access rules, không phải cách vượt quyền toàn cục. Các ví dụ runnable tìm method khai báo trong chính demo class nên quyền lookup hợp lệ.

## 4. Bản đồ các bộ biến đổi

| Combinator | Điều nó làm |
| --- | --- |
| `filterArguments` | Tiền xử lý một hoặc nhiều tham số bằng unary filters |
| `filterReturnValue` | Hậu xử lý kết quả của target |
| `insertArguments` | Đóng băng các tham số có giá trị biết trước |
| `dropArguments` | Thêm tham số ngoài mà target sẽ bỏ qua |
| `permuteArguments` | Hoán đổi, nhân bản hoặc bỏ qua tham số đầu vào |
| `guardWithTest` | Kiểm boolean rồi chọn target hoặc fallback |
| `catchException` | Nếu target ném exception matching, chuyển sang handler |
| `foldArguments` | Combiner tính một giá trị và target có thể dùng lại đầu vào gốc |
| `collectArguments` | Gộp nhiều inputs bằng filter rồi thay một target argument |
| `asSpreader` | Trải một array thành nhiều arguments |
| `asCollector` | Gom nhiều positional arguments thành một array |
| `asType` | Adapt bằng conversions được cho phép |
| `explicitCastArguments` | Adapt bằng explicit casts, có thể làm mất dữ liệu |
| `identity`, `constant`, `empty` | Tạo handles cơ bản để ghép tiếp |
| `countedLoop` | Xây vòng lặp theo số iterations |
| `tryFinally` | Bảo đảm cleanup sau target, kể cả khi target ném lỗi |

Với mỗi API, **đọc type trước và sau**, thay vì suy đoán từ tên combinator.

## 5. Chương trình A — FilterPipelineDemo.java

Dùng `filterArguments` đưa String vào parser trước khi gọi `square(int)`, rồi `filterReturnValue` đưa kết quả qua `label(int)`.

```java
import java.lang.invoke.*;
import static java.lang.invoke.MethodType.methodType;

public final class FilterPipelineDemo {
 public static int parse(String text){return Integer.parseInt(text);}
 public static int square(int x){return x*x;}
 public static String label(int n){return "value="+n;}

 public static void main(String[] args)throws Throwable{
   MethodHandles.Lookup lookup=MethodHandles.lookup();
   MethodHandle parse=lookup.findStatic(
       FilterPipelineDemo.class,"parse",
       methodType(int.class,String.class));
   MethodHandle square=lookup.findStatic(
       FilterPipelineDemo.class,"square",
       methodType(int.class,int.class));
   MethodHandle label=lookup.findStatic(
       FilterPipelineDemo.class,"label",
       methodType(String.class,int.class));

   MethodHandle filtered=
       MethodHandles.filterArguments(square,0,parse);
   MethodHandle pipeline=
       MethodHandles.filterReturnValue(filtered,label);
   System.out.println("signature="+pipeline.type());
   System.out.println("result="+
       (String)pipeline.invokeExact("7"));
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 FilterPipelineDemo.java
java FilterPipelineDemo
```

**Stdout đã kiểm thử:**

```text
signature=(String)String
result=value=49
```

**Giải thích:** Filter đầu vào nhận `(String)int` đúng chỗ target cần int, nên adapter `filtered` có type `(String)int`. Filter đầu ra `label` có `(int)String` đúng kiểu trả về của filtered, nên pipeline cuối là `(String)String`. Nếu input không parse được, exception được truyền lên; filter không tự xử lý lỗi.

## 6. insertArguments và dropArguments

`insertArguments(target,pos,values...)` tạo handle mới đã gán sẵn một hoặc nhiều đối số tại vị trí `pos`. Khi cố định đối số, nó **biến mất khỏi parameter list bên ngoài**.

`dropArguments(target,pos,classes...)` lại làm chiều ngược: adapter **nhận thêm** các đối số ở vị trí `pos` rồi bỏ qua chúng khi gọi target.

```text
decorate:           (String,int,String)String
insert prefix:      (int,String)String
insert suffix:      (int)String
drop dummy long:    (long,int)String
```

Cẩn thận: Sau khi bind một tham số, index của các tham số còn lại thay đổi. Đừng dùng index từ type cũ. Bind một object mutable cũng không làm nó immutable hoặc tự thread-safe.

## 7. Chương trình B — InsertDropDemo.java

```java
import java.lang.invoke.*;
import static java.lang.invoke.MethodType.methodType;

public final class InsertDropDemo{
 public static String decorate(String prefix,int n,String suffix){
   return prefix+n+suffix;
 }
 public static void main(String[] args)throws Throwable{
   MethodHandle base=MethodHandles.lookup().findStatic(
       InsertDropDemo.class,"decorate",
       methodType(String.class,
           String.class,int.class,String.class));
   MethodHandle prefix=
       MethodHandles.insertArguments(base,0,"ID:");
   MethodHandle both=
       MethodHandles.insertArguments(prefix,1,"!");
   MethodHandle extra=
       MethodHandles.dropArguments(both,0,long.class);

   System.out.println("signature="+extra.type());
   System.out.println("result="+
       (String)extra.invokeExact(999L,42));
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 InsertDropDemo.java
java InsertDropDemo
```

**Stdout đã kiểm thử:**

```text
signature=(long,int)String
result=ID:42!
```

`999L` được chấp nhận nhưng bỏ qua; `decorate` chỉ nhận prefix `"ID:"`, int 42 và suffix `"!"`.

## 8. permuteArguments: đổi thứ tự, nhân bản, bỏ qua

`permuteArguments(target,newType,reorder...)` lấy các incoming arguments của `newType` theo các indices trong `reorder` để gọi target:

- `[1,0]` đảo hai arguments.
- `[0,0]` dùng **cùng một argument** hai lần.
- `[0,2]` bỏ qua argument số 1 của incoming signature ba tham số.

Các ràng buộc: `reorder.length` bằng số tham số target, các indices hợp lệ trong `newType`; return type và kiểu tương ứng phải **giống chính xác**. Combinator này không tự parse, box hay chuyển String thành int.

## 9. Chương trình C — PermuteArgumentsDemo.java

```java
import java.lang.invoke.*;
import static java.lang.invoke.MethodType.methodType;

public final class PermuteArgumentsDemo{
 public static String join(String a,String b){return a+"|"+b;}
 public static void main(String[] args)throws Throwable{
   MethodHandle base=MethodHandles.lookup().findStatic(
       PermuteArgumentsDemo.class,"join",
       methodType(String.class,String.class,String.class));
   MethodHandle swapped=MethodHandles.permuteArguments(
       base,methodType(String.class,
           String.class,String.class),1,0);
   MethodHandle duplicate=MethodHandles.permuteArguments(
       base,methodType(String.class,String.class),0,0);
   MethodHandle ignored=MethodHandles.permuteArguments(
       base,methodType(String.class,
           String.class,String.class,String.class),0,2);
   System.out.println("swap="+
       (String)swapped.invokeExact("A","B"));
   System.out.println("duplicate="+
       (String)duplicate.invokeExact("X"));
   System.out.println("skipMiddle="+
       (String)ignored.invokeExact("P","ignored","Q"));
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 PermuteArgumentsDemo.java
java PermuteArgumentsDemo
```

**Stdout đã kiểm thử:**

```text
swap=B|A
duplicate=X|X
skipMiddle=P|Q
```

Duplication ở đây là nhân bản **reference/input**, không deep copy. Nếu reference chỉ tới object mutable, hai tham số có thể quan sát cùng state.

## 10. guardWithTest: rẽ nhánh

`guardWithTest(test,target,fallback)` tạo if/else động:

- `test` phải trả `boolean`.
- `target` và `fallback` có cùng `MethodType`.
- Test nhận một prefix compatible của tham số.
- Nếu test true gọi target; nếu false gọi fallback.
- Nếu test/nhánh throw exception, guard **không tự catch**; muốn xử lý phải kết hợp thêm `catchException`.

```text
isEven(int) -> boolean
  true  -> even(int) -> String
  false -> odd(int)  -> String
combined type: (int)String
```

## 11. Chương trình D — GuardWithTestDemo.java

```java
import java.lang.invoke.*;
import static java.lang.invoke.MethodType.methodType;

public final class GuardWithTestDemo{
 public static boolean isEven(int n){return n%2==0;}
 public static String even(int n){return n+":even";}
 public static String odd(int n){return n+":odd";}

 public static void main(String[] args)throws Throwable{
   MethodHandles.Lookup lookup=MethodHandles.lookup();
   MethodHandle pred=lookup.findStatic(
       GuardWithTestDemo.class,"isEven",
       methodType(boolean.class,int.class));
   MethodHandle a=lookup.findStatic(
       GuardWithTestDemo.class,"even",
       methodType(String.class,int.class));
   MethodHandle b=lookup.findStatic(
       GuardWithTestDemo.class,"odd",
       methodType(String.class,int.class));
   MethodHandle guarded=
       MethodHandles.guardWithTest(pred,a,b);
   System.out.println("signature="+guarded.type());
   System.out.println("four="+
       (String)guarded.invokeExact(4));
   System.out.println("five="+
       (String)guarded.invokeExact(5));
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 GuardWithTestDemo.java
java GuardWithTestDemo
```

**Stdout đã kiểm thử:**

```text
signature=(int)String
four=4:even
five=5:odd
```

Một guard không tự xác thực quyền truy cập hay tạo transaction. Hai nhánh có cùng chữ ký vẫn có thể có side effects rất khác nhau, cần test phù hợp.

## 12. catchException: xử lý một exception cụ thể

`catchException(target,exType,handler)` trả một handle cùng type target; khi target ném Throwable matching `exType`, handler được gọi.

```text
target:   (int,int)int
handler:  (ArithmeticException,int,int)int
adapted:  (int,int)int
```

Handler có tham số exception ở đầu, return type giống target, và có thể nhận một prefix đối số gốc. Nếu target thành công, handler không chạy. Exceptions không matching vẫn propagate.

Không catch `Throwable` quá rộng làm mất lỗi nghiêm trọng. Chọn policy có nghĩa: fallback sentinel như `-1` là ví dụ học tập, không tự đúng cho mọi business domain.

## 13. Chương trình E — CatchExceptionDemo.java

```java
import java.lang.invoke.*;
import static java.lang.invoke.MethodType.methodType;

public final class CatchExceptionDemo{
 public static int divide(int a,int b){return a/b;}
 public static int fallback(
     ArithmeticException exception,int a,int b){
   return -1;
 }
 public static void main(String[] args)throws Throwable{
   MethodHandles.Lookup lookup=MethodHandles.lookup();
   MethodHandle div=lookup.findStatic(
       CatchExceptionDemo.class,"divide",
       methodType(int.class,int.class,int.class));
   MethodHandle catcher=lookup.findStatic(
       CatchExceptionDemo.class,"fallback",
       methodType(int.class,
           ArithmeticException.class,int.class,int.class));
   MethodHandle safe=MethodHandles.catchException(
       div,ArithmeticException.class,catcher);
   System.out.println("normal="+
       (int)safe.invokeExact(8,2));
   System.out.println("zero="+
       (int)safe.invokeExact(8,0));
   System.out.println("signature="+safe.type());
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 CatchExceptionDemo.java
java CatchExceptionDemo
```

**Stdout đã kiểm thử:**

```text
normal=4
zero=-1
signature=(int,int)int
```

`ArithmeticException` được bắt trong phép chia zero; việc trả `-1` chỉ cho thấy cách lắp handler. Trong hệ thống thực, nếu -1 là giá trị hợp lệ hoặc lỗi cần được ghi nhận, không dùng sentinel âm thầm.

## 14. foldArguments: precompute và vẫn dùng inputs gốc

`foldArguments(target,combiner)` tính một giá trị bằng combiner, đưa giá trị đó vào target nhưng vẫn có thể truyền các arguments gốc cho target.

Ví dụ:
- `multiply(a,b)` → product.
- `combine(product,a,b)` → product+a+b.
- Folded handle có type `(int,int)int`, ứng với hàm `a*b+a+b`.

Cần dùng đúng type/layout; combiner không phải filter tùy ý. Combiner được thực hiện trước target, nên nếu combiner ném exception, target không chạy.

## 15. Chương trình F — FoldArgumentsDemo.java

```java
import java.lang.invoke.*;
import static java.lang.invoke.MethodType.methodType;

public final class FoldArgumentsDemo{
 public static int multiply(int a,int b){return a*b;}
 public static int combine(int product,int a,int b){
   return product+a+b;
 }
 public static void main(String[] args)throws Throwable{
   MethodHandles.Lookup l=MethodHandles.lookup();
   MethodHandle mul=l.findStatic(
       FoldArgumentsDemo.class,"multiply",
       methodType(int.class,int.class,int.class));
   MethodHandle comb=l.findStatic(
       FoldArgumentsDemo.class,"combine",
       methodType(int.class,int.class,int.class,int.class));
   MethodHandle fold=MethodHandles.foldArguments(comb,mul);
   System.out.println("signature="+fold.type());
   System.out.println("result="+
       (int)fold.invokeExact(3,4));
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 FoldArgumentsDemo.java
java FoldArgumentsDemo
```

**Stdout đã kiểm thử:**

```text
signature=(int,int)int
result=19
```

`3*4+3+4=19`. Đây là ví dụ hữu ích để phân biệt fold với việc chỉ thay input bằng output filter.

## 16. collectArguments: tiền xử lý nhiều inputs

`collectArguments(target,pos,filter)` lấy một chuỗi các tham số từ lời gọi ngoài, truyền vào filter, rồi đặt kết quả của filter vào một vị trí target.

```text
combine: (String a,String b)String -> "A-B"
wrap:    (String combined,String suffix)String -> "[A-B]!"
collectArguments(wrap,0,combine):
         (String,String,String)String
```

Khác với `foldArguments`, target trong ví dụ chỉ cần **kết quả đã gộp** và suffix, không dùng lại A/B dưới dạng hai arguments riêng.

**Đừng nhầm tên:** `collectArguments` là static method thuộc `MethodHandles`, còn `asCollector` là instance method trên `MethodHandle` chuyên gom positional arguments thành một array.

## 17. Chương trình G — CollectArgumentsDemo.java

```java
import java.lang.invoke.*;
import static java.lang.invoke.MethodType.methodType;

public final class CollectArgumentsDemo{
 public static String combine(String a,String b){
   return a+"-"+b;
 }
 public static String wrap(String combined,String suffix){
   return "["+combined+"]"+suffix;
 }
 public static void main(String[] args)throws Throwable{
   MethodHandles.Lookup l=MethodHandles.lookup();
   MethodHandle filt=l.findStatic(
       CollectArgumentsDemo.class,"combine",
       methodType(String.class,String.class,String.class));
   MethodHandle target=l.findStatic(
       CollectArgumentsDemo.class,"wrap",
       methodType(String.class,String.class,String.class));
   MethodHandle collected=
       MethodHandles.collectArguments(target,0,filt);
   System.out.println("signature="+collected.type());
   System.out.println("result="+
       (String)collected.invokeExact("A","B","!"));
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 CollectArgumentsDemo.java
java CollectArgumentsDemo
```

**Stdout đã kiểm thử:**

```text
signature=(String,String,String)String
result=[A-B]!
```

Filter `combine` tiêu thụ hai Strings và trả một String. Wrapper vẫn nhận một suffix String để tạo kết quả.

## 18. Array adapters: asSpreader và asCollector

`handle.asSpreader(String[].class,3)` biến một handle nhận ba Strings thành handle nhận **một String[]**. Ngược lại, `handle.asCollector(String[].class,3)` biến một handle nhận String[] thành handle nhận **ba Strings** rồi tạo array khi gọi target.

```text
join:         (String,String,String)String
asSpreader:   (String[])String

bracket:      (String[])String
asCollector:  (String,String,String)String
```

Hãy dùng đúng array type/count; nếu spread array với length không đúng số phần tử cần, adapter có thể ném `IllegalArgumentException`. Đây là adaptation của **method-call arity**, không phải Java Stream collector.

## 19. Chương trình H — SpreadCollectDemo.java

```java
import java.lang.invoke.*;
import java.util.Arrays;
import static java.lang.invoke.MethodType.methodType;

public final class SpreadCollectDemo{
 public static String join(String a,String b,String c){
   return a+"-"+b+"-"+c;
 }
 public static String bracket(String[] items){
   return "["+String.join(",",items)+"]";
 }
 public static void main(String[] args)throws Throwable{
   MethodHandles.Lookup l=MethodHandles.lookup();
   MethodHandle three=l.findStatic(
       SpreadCollectDemo.class,"join",
       methodType(String.class,
           String.class,String.class,String.class));
   MethodHandle spread=three.asSpreader(String[].class,3);
   MethodHandle array=l.findStatic(
       SpreadCollectDemo.class,"bracket",
       methodType(String.class,String[].class));
   MethodHandle collect=array.asCollector(String[].class,3);
   System.out.println("spreader="+
       (String)spread.invokeExact(
           new String[]{"A","B","C"}));
   System.out.println("collector="+
       (String)collect.invokeExact("X","Y","Z"));
   System.out.println("spreaderType="+spread.type());
   System.out.println("collectorType="+collect.type());
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 SpreadCollectDemo.java
java SpreadCollectDemo
```

**Stdout đã kiểm thử:**

```text
spreader=A-B-C
collector=[X,Y,Z]
spreaderType=(String[])String
collectorType=(String,String,String)String
```

`Arrays` được import nhưng không cần dùng ở ví dụ, không ảnh hưởng biên dịch. Ứng dụng production có thể kết hợp permuteArguments với spread/collect, nhưng phải theo dõi lại signatures.

## 20. asType: các phép chuyển kiểu có điều kiện

`MethodHandle.asType(newType)` tạo adapter có thể thực hiện boxing, unboxing, primitive widening và reference casting khi phù hợp theo MethodHandle conversion rules.

Ví dụ `doubled(int)int` thành `(Integer)long`:
- Nhận `Integer`.
- Unbox thành `int`.
- Gọi `doubled`.
- Widen kết quả `int` thành `long`.

**Không có tự động parse String thành int.** `asType` không thể thay thế `Integer.parseInt`.

### 20.1. Khi nào xảy ra lỗi?

Một conversion không được phép có thể làm `asType` ném `WrongMethodTypeException` ngay khi dựng adapter. Một conversion allowed về mặt type nhưng giá trị runtime không hợp lệ có thể ném `ClassCastException` hoặc `NullPointerException` tại invocation.

## 21. Chương trình I — AsTypeDemo.java

```java
import java.lang.invoke.*;
import static java.lang.invoke.MethodType.methodType;

public final class AsTypeDemo{
 public static int doubled(int n){return n*2;}
 public static void main(String[] args)throws Throwable{
   MethodHandle original=MethodHandles.lookup().findStatic(
       AsTypeDemo.class,"doubled",
       methodType(int.class,int.class));
   MethodHandle adapted=original.asType(
       methodType(long.class,Integer.class));
   boolean invalidRejected=false;
   try{
     original.asType(
         methodType(int.class,String.class));
   }catch(WrongMethodTypeException expected){
     invalidRejected=true;
   }
   System.out.println("adaptedType="+adapted.type());
   System.out.println("adaptedValue="+
       (long)adapted.invokeExact(Integer.valueOf(6)));
   System.out.println("invalidAdaptationRejected="+
       invalidRejected);
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 AsTypeDemo.java
java AsTypeDemo
```

**Stdout đã kiểm thử:**

```text
adaptedType=(Integer)long
adaptedValue=12
invalidAdaptationRejected=true
```

Nếu thật sự muốn xử lý chuỗi `"6"`, viết `parse(String)int` rồi sử dụng `filterArguments`. Không cố “lách” giới hạn bằng unchecked casts.

## 22. invokeExact yêu cầu cả type của return expression

`MethodHandle.invokeExact` là method signature-polymorphic. Static type của input/return tại **chỗ gọi** quyết định method type mà JVM yêu cầu.

Giả sử một handle thực sự có type `(int)int`:

```java
int value=(int)handle.invokeExact(3);      // exact
long x=(long)handle.invokeExact(3);       // wrong return at call site
int y=(int)handle.invokeExact("3");       // wrong argument at call site
```

Đây là **mảnh minh họa**, chưa định nghĩa `handle`. Hai dòng sau sẽ ném `WrongMethodTypeException` khi gọi mà không có adaptation phù hợp, dù Java có các primitive conversions ở những ngữ cảnh khác.

## 23. Chương trình J — InvokeExactTypesDemo.java

```java
import java.lang.invoke.*;
import static java.lang.invoke.MethodType.methodType;

public final class InvokeExactTypesDemo{
 public static int inc(int v){return v+1;}
 public static void main(String[] args)throws Throwable{
   MethodHandle handle=MethodHandles.lookup().findStatic(
       InvokeExactTypesDemo.class,"inc",
       methodType(int.class,int.class));
   boolean caught=false;
   try{
     int ignored=(int)handle.invokeExact("3");
   }catch(WrongMethodTypeException expected){
     caught=true;
   }
   System.out.println("exact="+
       (int)handle.invokeExact(3));
   System.out.println("wrongMethodTypeCaught="+caught);
   System.out.println("reportedType="+handle.type());
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 InvokeExactTypesDemo.java
java InvokeExactTypesDemo
```

**Stdout đã kiểm thử:**

```text
exact=4
wrongMethodTypeCaught=true
reportedType=(int)int
```

Lỗi ở `"3"` không phải do parse thất bại; **không có bước parse nào được gọi**. Caller yêu cầu chữ ký `(String)int` nhưng handle là `(int)int`.

## 24. identity, constant, empty: mảnh ghép cơ bản

- `MethodHandles.identity(int.class)` → `(int)int`, trả input.
- `MethodHandles.constant(String.class,"READY")` → `()String`, trả hằng.
- `MethodHandles.empty(methodType(int.class))` → `()int`, trả 0.
- `dropArguments` có thể biến constant thành callback có nhiều tham số bị bỏ qua.

`empty` được thêm từ Java 9 và vẫn dùng trên Java 17. Nó tạo giá trị mặc định (zero/null/void) **không phải một fallback có nghĩa nghiệp vụ**. Đừng mặc định 0 là kết quả thành công nếu input bị lỗi.

## 25. Chương trình K — ConstantIdentityDemo.java

```java
import java.lang.invoke.*;
import static java.lang.invoke.MethodType.methodType;

public final class ConstantIdentityDemo{
 public static void main(String[] args)throws Throwable{
   MethodHandle constant=
       MethodHandles.constant(String.class,"READY");
   MethodHandle identity=
       MethodHandles.identity(int.class);
   MethodHandle ignored=
       MethodHandles.dropArguments(
           constant,0,int.class,boolean.class);
   System.out.println("constant="+
       (String)constant.invokeExact());
   System.out.println("identity="+
       (int)identity.invokeExact(9));
   System.out.println("ignored="+
       (String)ignored.invokeExact(7,false));
   System.out.println("emptyInteger="+
       (int)MethodHandles.empty(
           methodType(int.class)).invokeExact());
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ConstantIdentityDemo.java
java ConstantIdentityDemo
```

**Stdout đã kiểm thử:**

```text
constant=READY
identity=9
ignored=READY
emptyInteger=0
```

Có thể dùng `dropArguments(constant,0,...)` để tạo một fallback nhánh guard nhận type mong muốn, nhưng nếu cần context hoặc logging hãy dùng handler thực sự.

## 26. Ghép nhiều biến đổi thành pipeline có validation và recovery

Mục tiêu: nhận String, parse thành int, rẽ nhánh dương/âm, trả một String; nếu parse thất bại, trả thông báo riêng.

```text
                input String
                    |
            parse(String)int
                    |
            guardWithTest(int)
               /          \
         nonnegative      negative
             |               |
            "ok:n"      "negative:n"
               \          /
                 String result
                      |
     catchException(NumberFormatException)
                      |
                 "invalid:..."
```

Cụ thể:
1. `guardWithTest` trên `(int)boolean` và hai nhánh `(int)String`.
2. `filterArguments(guarded,0,parse)` thành `(String)String`.
3. `catchException(parsed,NumberFormatException,handler)` vẫn là `(String)String`.

**Thứ tự wrapping rất quan trọng**: Nếu `catchException` chỉ bọc guard trước khi parse được chèn vào, exception từ parser có thể nằm **ngoài** phạm vi catch.

## 27. Chương trình L — ComposedPipelineDemo.java

```java
import java.lang.invoke.*;
import static java.lang.invoke.MethodType.methodType;

public final class ComposedPipelineDemo{
 public static int parse(String s){return Integer.parseInt(s);}
 public static boolean nonnegative(int n){return n>=0;}
 public static String positive(int n){return "ok:"+n;}
 public static String negative(int n){return "negative:"+n;}
 public static String recover(NumberFormatException e,String s){
   return "invalid:"+s;
 }

 public static void main(String[] args)throws Throwable{
   MethodHandles.Lookup l=MethodHandles.lookup();
   MethodHandle parse=l.findStatic(
       ComposedPipelineDemo.class,"parse",
       methodType(int.class,String.class));
   MethodHandle pred=l.findStatic(
       ComposedPipelineDemo.class,"nonnegative",
       methodType(boolean.class,int.class));
   MethodHandle a=l.findStatic(
       ComposedPipelineDemo.class,"positive",
       methodType(String.class,int.class));
   MethodHandle b=l.findStatic(
       ComposedPipelineDemo.class,"negative",
       methodType(String.class,int.class));
   MethodHandle guarded=
       MethodHandles.guardWithTest(pred,a,b);
   MethodHandle parsed=
       MethodHandles.filterArguments(guarded,0,parse);
   MethodHandle handler=l.findStatic(
       ComposedPipelineDemo.class,"recover",
       methodType(String.class,
           NumberFormatException.class,String.class));
   MethodHandle safe=MethodHandles.catchException(
       parsed,NumberFormatException.class,handler);
   System.out.println("type="+safe.type());
   System.out.println("ok="+
       (String)safe.invokeExact("12"));
   System.out.println("negative="+
       (String)safe.invokeExact("-3"));
   System.out.println("bad="+
       (String)safe.invokeExact("abc"));
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ComposedPipelineDemo.java
java ComposedPipelineDemo
```

**Stdout đã kiểm thử:**

```text
type=(String)String
ok=ok:12
negative=negative:-3
bad=invalid:abc
```

Cùng một pipeline handle xử lý ba luồng: thành công, nhánh âm, và lỗi parse. Đây là minh họa exception recovery có chủ ý; production nên có error type và validation policy rõ ràng.

## 28. bindTo: cố định receiver của virtual method

`lookup.findVirtual(String.class,"concat", methodType(String.class,String.class))` tạo handle có receiver ở đầu, type `(String,String)String`. `bindTo("Hi, ")` cố định receiver và trả `(String)String`.

`bindTo` áp dụng cho tham số reference đầu tiên. Muốn bind primitive hoặc tham số ở vị trí khác, dùng `insertArguments`.

## 29. Chương trình M — BindToDemo.java

```java
import java.lang.invoke.*;
import static java.lang.invoke.MethodType.methodType;

public final class BindToDemo{
 public static void main(String[] args)throws Throwable{
   MethodHandle concat=MethodHandles.lookup().findVirtual(
       String.class,"concat",
       methodType(String.class,String.class));
   MethodHandle bound=concat.bindTo("Hi, ");
   System.out.println("type="+bound.type());
   System.out.println("output="+
       (String)bound.invokeExact("Java"));
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 BindToDemo.java
java BindToDemo
```

**Stdout đã kiểm thử:**

```text
type=(String)String
output=Hi, Java
```

Với mutable receiver, bound handle giữ reference và có thể quan sát những thay đổi cùng side effects; không có deep copy.

## 30. countedLoop: bộ biến đổi biểu diễn vòng lặp

`MethodHandles.countedLoop(iterations,init,body)` xuất hiện từ Java 9, còn hiện hành trên Java 17.

- `iterations` trả `int` số vòng chạy.
- `init` khởi tạo một loop variable, có thể null để dùng default.
- `body` nhận state hiện tại và chỉ số vòng `int`, trả state mới (khi return non-void).
- Counter bắt đầu 0 và tăng đến hết số vòng.
- Có overload start/end cho range khác.

```text
n = 4, initial sum = 0
i=0 -> sum=1
i=1 -> sum=3
i=2 -> sum=6
i=3 -> sum=10
return 10
```

Một vòng for thường dễ đọc hơn khi xử lý code tĩnh. Loop combinator hữu ích cho framework cần **tạo động** chuỗi hành vi hoàn toàn dưới dạng MethodHandles.

## 31. Chương trình N — CountedLoopDemo.java

```java
import java.lang.invoke.*;
import static java.lang.invoke.MethodType.methodType;

public final class CountedLoopDemo{
 public static int step(int sum,int index){
   return sum+index+1;
 }
 public static void main(String[] args)throws Throwable{
   MethodHandle n=MethodHandles.identity(int.class);
   MethodHandle body=MethodHandles.lookup().findStatic(
       CountedLoopDemo.class,"step",
       methodType(int.class,int.class,int.class));
   MethodHandle loop=
       MethodHandles.countedLoop(n,null,body);
   System.out.println("type="+loop.type());
   System.out.println("sum4="+
       (int)loop.invokeExact(4));
   System.out.println("sum0="+
       (int)loop.invokeExact(0));
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 CountedLoopDemo.java
java CountedLoopDemo
```

**Stdout đã kiểm thử:**

```text
type=(int)int
sum4=10
sum0=0
```

`identity(int.class)` làm handle lấy số iterations. `init=null` tạo state khởi đầu 0, sau mỗi vòng `step(sum,index)` tăng bằng `index+1`.

## 32. tryFinally: cleanup không đồng nghĩa exception recovery

`MethodHandles.tryFinally(target,cleanup)` (Java 9+) gọi cleanup dù target thành công hay ném Throwable. Quy tắc signature:

- Cleanup nhận `Throwable` đầu tiên: `null` khi bình thường, exception thật khi target thất bại.
- Nếu target có return non-void, cleanup nhận **giá trị kết quả** thứ hai (hoặc default value placeholder khi target throw).
- Cleanup có thể nhận tiếp prefix arguments gốc.
- Cleanup có **cùng return type** với target, vì có thể thay return value khi target thành công.
- Nếu target throw, exception vẫn được rethrow trừ khi cleanup throw exception khác trước.

```text
target:  (int)int
cleanup: (Throwable,int result,int input)int
adapter: (int)int
```

`tryFinally` **không** được dùng thay `catchException` để biến failure thành success. Nếu cleanup throw khi đang xử lý một lỗi khác, exception cleanup có thể che root cause, nên cần error strategy rõ.

## 33. Chương trình O — TryFinallyDemo.java

```java
import java.lang.invoke.*;
import static java.lang.invoke.MethodType.methodType;

public final class TryFinallyDemo{
 static int cleanups=0;
 static boolean sawFailure=false;
 public static int risky(int n){
   if(n<0)throw new IllegalArgumentException("negative");
   return n*3;
 }
 public static int cleanup(Throwable problem,int original,int n){
   cleanups++;
   if(problem!=null)sawFailure=true;
   return original+1;
 }
 public static void main(String[] args)throws Throwable{
   MethodHandles.Lookup l=MethodHandles.lookup();
   MethodHandle action=l.findStatic(
       TryFinallyDemo.class,"risky",
       methodType(int.class,int.class));
   MethodHandle cleanup=l.findStatic(
       TryFinallyDemo.class,"cleanup",
       methodType(int.class,
           Throwable.class,int.class,int.class));
   MethodHandle mh=MethodHandles.tryFinally(action,cleanup);
   System.out.println("type="+mh.type());
   System.out.println("normal="+
       (int)mh.invokeExact(4));
   boolean threw=false;
   try{
     int ignored=(int)mh.invokeExact(-1);
   }catch(IllegalArgumentException e){
     threw=true;
   }
   System.out.println("exceptionRethrown="+threw);
   System.out.println("cleanupCount="+cleanups);
   System.out.println("cleanupSawFailure="+sawFailure);
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 TryFinallyDemo.java
java TryFinallyDemo
```

**Stdout đã kiểm thử:**

```text
type=(int)int
normal=13
exceptionRethrown=true
cleanupCount=2
cleanupSawFailure=true
```

Đường thành công tạo 12 rồi cleanup trả 13. Đường lỗi vẫn chạy cleanup nhưng `IllegalArgumentException` được rethrow. Biến static counters của demo chỉ phục vụ một thread; nếu gọi handle đồng thời, phải đồng bộ shared state.

## 34. explicitCastArguments: ép kiểu tường minh có thể mất dữ liệu

`MethodHandles.explicitCastArguments(target,newType)` thích nghi kiểu bằng explicit casts, có thể cho phép narrowing bị `asType` từ chối.

`int 130` cast sang `byte` sẽ thành `-126`, vì `byte` có 8 bits signed. Nếu code dùng ID, tiền, tuổi hoặc security values, đây có thể là **lỗi dữ liệu nghiêm trọng**. Chỉ dùng explicit narrowing khi có ý thức và test range/truncation.

## 35. Chương trình P — ExplicitCastDemo.java

```java
import java.lang.invoke.*;
import static java.lang.invoke.MethodType.methodType;

public final class ExplicitCastDemo{
 public static byte echo(byte v){return v;}
 public static void main(String[] args)throws Throwable{
   MethodHandle byteEcho=MethodHandles.lookup().findStatic(
       ExplicitCastDemo.class,"echo",
       methodType(byte.class,byte.class));
   MethodHandle cast=MethodHandles.explicitCastArguments(
       byteEcho,methodType(int.class,int.class));
   boolean noAsType=false;
   try{
     byteEcho.asType(
         methodType(int.class,int.class));
   }catch(WrongMethodTypeException e){
     noAsType=true;
   }
   System.out.println("type="+cast.type());
   System.out.println("narrowed130="+
       (int)cast.invokeExact(130));
   System.out.println("asTypeNarrowingRejected="+noAsType);
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ExplicitCastDemo.java
java ExplicitCastDemo
```

**Stdout đã kiểm thử:**

```text
type=(int)int
narrowed130=-126
asTypeNarrowingRejected=true
```

Phép ép kiểu hợp lệ với JVM không có nghĩa đúng với domain. Nếu muốn từ chối overflow, hãy dùng validation hoặc checked conversion thay vì ép hẹp âm thầm.

## 36. So sánh các bộ biến đổi thường bị nhầm

| Nhu cầu | API |
| --- | --- |
| Unary filter trên từng tham số | `filterArguments` |
| Hậu xử lý kết quả | `filterReturnValue` |
| Nhiều inputs được filter thành một argument của target | `collectArguments` |
| Combiner tính giá trị nhưng target vẫn có thể dùng lại inputs gốc | `foldArguments` |
| Gom positional arguments thành array | `asCollector` |
| Trải một array thành positional arguments | `asSpreader` |
| Chốt argument đã biết | `insertArguments` |
| Chấp nhận argument không sử dụng | `dropArguments` |
| Đảo/nhân bản/bỏ qua input positions | `permuteArguments` |
| Chọn một trong hai nhánh theo boolean predicate | `guardWithTest` |
| Recover từ exception matching | `catchException` |
| Always cleanup (thành công hoặc lỗi) | `tryFinally` |
| Boxing/unboxing/widening/casting được hỗ trợ | `asType` |
| Explicit narrowing có kiểm soát | `explicitCastArguments` |

**Sai lầm lớn:** Vì tên có chữ collect/fold/filter nên nghĩ chúng interchangeable. Mỗi combinator có quy tắc **vị trí, số tham số, kiểu trả về** khác nhau.

## 37. Lỗi tạo adapter và lỗi khi gọi handle

| Lỗi | Khi nào |
| --- | --- |
| `NoSuchMethodException` | `findStatic/findVirtual` không tìm method có signature chính xác |
| `IllegalAccessException` | Lookup không đủ quyền truy cập |
| `IllegalArgumentException` | Combinator types/positions/count không hợp lệ |
| `WrongMethodTypeException` | `asType` conversion bất hợp lệ hoặc `invokeExact` call-site type sai |
| `ClassCastException` | Runtime reference cast sai khi conversion được phép về mặt type |
| `NullPointerException` | Unboxing null, hoặc tham số API cần non-null |
| `NumberFormatException` | Target/parser ném khi text không phải số |
| `ArithmeticException` | Target division by zero |
| Throwable từ cleanup | `tryFinally` cleanup có thể ném và che root cause |

Đừng catch `Throwable` rộng rồi luôn return default như thể không có lỗi. Lỗi ở **adapter construction** thường là lỗi lập trình/configuration cần sửa, còn lỗi ở **target invocation** có thể là lỗi dữ liệu/nghiệp vụ cần chính sách xử lý.

### 37.1. invoke khác invokeExact

`invokeExact` đòi exact call-site type. `invoke` có thể cho phép conversions phù hợp với `asType`. `invokeWithArguments` là generic bridge có thể phải box/convert/allocate, không nên dùng vô cớ ở hot path.

`MethodHandle` thường ném trực tiếp exceptions của target, không mặc nhiên bọc trong `InvocationTargetException` như `Method.invoke` reflection. Chọn catch theo API được gọi.

### 37.2. MethodType khác parameter names

`MethodType` chỉ lưu types/arity, không mô tả tên business. Hai tham số cùng `String` có thể bị đảo mà vẫn type-correct, nhưng logic có thể sai. Unit tests cần kiểm **semantic output**, không chỉ type.

## 38. Tư duy xây pipeline an toàn

Bước 1: Viết `MethodType` của target và desired external signature.

Bước 2: Phân loại thay đổi:
- Đầu vào/đầu ra → filters.
- Arity/position → insert/drop/permute/collector/spreader.
- Branch/error → guard/catch/tryFinally.
- Loop → countedLoop hoặc logic Java bình thường.

Bước 3: Sau mỗi combinator, kiểm `handle.type()` và các điều kiện `MethodType`.

Bước 4: Test happy path, invalid data, exception paths, nulls, overflow, argument positions, array lengths và side effects.

Bước 5: Dùng `invokeExact` với kiểu trả về đúng. Không dùng unchecked conversion để “dập” mismatch.

Bước 6: Cache handle sau khi cấu hình nếu dùng lại; lookup/adapter construction không nên bị lặp vô cớ trong hot loop.

Bước 7: Nếu target chứa mutable state, đảm bảo thread safety và ownership ở chính target/receiver.

## 39. Thứ tự bộ biến đổi ảnh hưởng exception scope

Xét:

```text
catchException(filterArguments(target,parse),handler):
  catches exceptions from parse AND target.

filterArguments(catchException(target,handler),parse):
  catches exceptions from target, NOT parser.
```

Tương tự:
- `guardWithTest` fallback chỉ được chọn khi predicate false, không phải target throw.
- `tryFinally` cleanup vẫn chạy khi target throw nhưng exception vẫn propagate.
- `foldArguments` combiner side effect xảy ra trước target; target throw không rollback combiner.
- `collectArguments` filter throw thì target chưa chạy.
- `permuteArguments` có thể đổi semantic của side effects khi target nhận arguments theo thứ tự khác.
- `insertArguments` có thể giữ reference tới mutable/privileged object lâu dài.

Khi dùng cho database, file, network hoặc tài nguyên có side effect, một chain MethodHandle **không cung cấp atomic transaction**. Phải quản lý transaction/cleanup/retry/idempotency ở application layer.

## 40. Thread safety, quyền truy cập và hiệu năng

Một `MethodHandle` có thể được tái sử dụng từ nhiều threads, nhưng các methods/receiver/filters được gọi **không tự thread-safe**. Nếu bind mutable object, counter hoặc service có shared state, cần synchronization, immutable configuration hoặc thread confinement.

Về bảo mật:
- Lookup tuân quyền caller, module boundaries.
- Không sử dụng reflection/Unsafe để truy cập private JDK internals.
- Không nhận tên class/method tùy ý từ user rồi tạo privileged handle.
- Binding một object có quyền cao vào handle rồi chia sẻ handle có thể làm lộ capability.
- `WrongMethodTypeException` là type check, **không phải authorization check**.

Về hiệu năng:
- JIT có thể optimize/inlining, nhưng không bảo đảm mọi chain nhanh hơn direct call hoặc lambda.
- Đừng tạo lại lookup/handles mỗi request nếu pipeline ổn định.
- Đo throughput/latency bằng benchmark có warm-up như JMH, không dùng một lần `System.nanoTime()`.
- `invokeWithArguments` có thể có overhead boxing/array conversions.
- Với code nghiệp vụ tĩnh đơn giản, một method Java/lambda thường dễ đọc và bảo trì hơn.

## 41. Ma trận kiểm thử 16 chương trình

| Chương trình | Điều đã kiểm | Kết quả |
| --- | --- | --- |
| `FilterPipelineDemo` | filter input/output | `(String)String`, value=49 |
| `InsertDropDemo` | bind và ignore arguments | `(long,int)String`, ID:42! |
| `PermuteArgumentsDemo` | reorder, duplicate, skip | B\|A, X\|X, P\|Q |
| `GuardWithTestDemo` | if/else bằng predicate | 4:even, 5:odd |
| `CatchExceptionDemo` | exception handler | normal 4, divide zero -1 |
| `FoldArgumentsDemo` | tính trước và tái sử dụng input | result 19 |
| `CollectArgumentsDemo` | multi-argument filter | [A-B]! |
| `SpreadCollectDemo` | array-vs-positions | A-B-C, [X,Y,Z] |
| `AsTypeDemo` | boxing/unboxing/widening | value 12, invalid rejected |
| `InvokeExactTypesDemo` | exact call-site signature | correct 4, wrong exception |
| `ConstantIdentityDemo` | constant/identity/empty | READY/9/READY/0 |
| `ComposedPipelineDemo` | guard/filter/catch | ok/negative/invalid |
| `BindToDemo` | virtual receiver binding | Hi, Java |
| `CountedLoopDemo` | counted loop state | sum4 10, sum0 0 |
| `TryFinallyDemo` | cleanup normal/error | cleanup2, exception rethrown |
| `ExplicitCastDemo` | explicit narrowing | int 130→-126 |

Các classes độc lập trên đã được kiểm thử bằng `javac --release 17 -encoding UTF-8` và chạy thành công; stdout ghi trong từng ví dụ là output thực đã xác minh. Ví dụ dùng public Java SE 17 APIs, không cần thư viện bên ngoài, server hay kết nối mạng.

**Không assert:** runtime method-handle performance cố định, thread scheduling, internal JVM implementation details, một conversion được phép sẽ luôn đúng về nghiệp vụ.

**Nên assert:** `handle.type()`, kết quả happy path, đúng exception type, cleanup, overload/arity và bản chất side effects.

## 42. Những lỗi phổ biến

1. Nghĩ `MethodHandle` giống hệt `java.lang.reflect.Method`.
2. Không kiểm type sau khi filter/insert/permute.
3. Bỏ return cast trong `invokeExact`.
4. Dùng `invokeExact` như `invoke` rồi mong tự boxing.
5. Mong `asType` parse String thành số.
6. Dùng `explicitCastArguments` và bỏ qua overflow.
7. Chọn sai vị trí sau khi insertArguments đã làm giảm arity.
8. Hiểu `dropArguments` là xóa một tham số gốc.
9. Hiểu `permuteArguments` reorder từ target thay vì newType.
10. Nghĩ `permuteArguments` tự ép kiểu.
11. Truyền filter không unary vào `filterArguments`.
12. Cho guard predicate trả String thay vì boolean.
13. Hai guard branches khác MethodType.
14. Nghĩ guard fallback chạy khi target throw.
15. Handler của catchException khác return type target.
16. Bắt Throwable quá rộng và che lỗi quan trọng.
17. Cho rằng `tryFinally` recover exception.
18. Cleanup ném lỗi mới che lỗi gốc.
19. Nhầm `collectArguments` với `asCollector`.
20. Nhầm `foldArguments` với filterArguments.
21. Sai array type/count của asSpreader/asCollector.
22. Nghĩ bindTo áp dụng cho mọi tham số primitive.
23. Giữ mutable bound object không có thread-safety policy.
24. Dùng lookup để vượt private/module access.
25. Kỳ vọng một MethodHandle có quyền cao an toàn khi chia sẻ tùy ý.
26. Dựng lại chain ở mỗi lần gọi và bỏ qua chi phí setup.
27. Benchmark không warm-up hoặc không có control group.
28. Dùng MethodHandles cho code tĩnh đơn giản làm mất readability.
29. Bỏ qua exception path khi kết hợp parser/guard/fallback.
30. Dùng type compatibility làm thay business validation.
31. Bỏ transaction policy khi target có side effects.
32. Nhầm method handles tạo từ Java 9+ là feature đã có ở Java 7.
33. Lạm dụng invokeWithArguments trong hot loop.
34. Dùng unchecked casts che code bug.
35. Không test module/classloader access khi deploy.

## 43. Bài tập có đáp án

**1.** `MethodType` lưu điều gì? **Return type và danh sách parameter types theo thứ tự**.

**2.** `filterArguments` khác `filterReturnValue`? **Lọc input trước target và output sau target**.

**3.** `(int)int` lọc bằng `(String)int` thành type gì? **`(String)int`**.

**4.** Thêm filter `(int)String` cho kết quả thành type gì? **`(String)String`**.

**5.** `insertArguments` làm gì? **Bind giá trị vào vị trí, giảm parameters bên ngoài**.

**6.** `dropArguments` có làm target nhận thêm dữ liệu không? **Không; adapter nhận rồi bỏ qua**.

**7.** reorder `[1,0]`? **Đảo hai input positions**.

**8.** reorder `[0,0]`? **Nhân bản cùng input reference vào hai positions**.

**9.** `guardWithTest` test trả kiểu nào? **boolean**.

**10.** Guard target/fallback cần có type ra sao? **Cùng MethodType**.

**11.** Target của guard throw thì fallback có chạy tự động không? **Không**.

**12.** `catchException` có thể bắt một exception class cụ thể không? **Có**.

**13.** Handler catchException phải trả gì? **Cùng return type với target**.

**14.** `foldArguments` có thể truyền lại original inputs vào target không? **Có**.

**15.** `collectArguments` dùng khi nào? **Nhiều inputs thành một argument cho target**.

**16.** `asCollector` khác collectArguments? **Gom positional arguments thành array**.

**17.** `asSpreader` biến ba Strings thành input kiểu gì? **String[]**.

**18.** `asType` có làm Integer→int→long được không? **Có, conversions phù hợp**.

**19.** `asType` có String→int kiểu parse số không? **Không**.

**20.** `invokeExact` yêu cầu return type đúng không? **Có**.

**21.** WrongMethodTypeException là lỗi quyền truy cập hay type? **Type mismatch**.

**22.** `identity(int.class).invokeExact(9)` trả? **9**.

**23.** `constant(String.class,"READY")` cần mấy tham số? **Không có**.

**24.** `empty(methodType(int.class))` trả gì? **0**.

**25.** `bindTo` trên String.concat bind thành phần gì? **Receiver reference đầu tiên**.

**26.** `countedLoop` sum 1..4 là bao nhiêu? **10**.

**27.** `tryFinally` có chạy cleanup khi target throw không? **Có**.

**28.** Cleanup return bình thường khi target throw có biến lỗi thành success không? **Không**.

**29.** `explicitCastArguments` int130→byte→int ra? **-126**.

**30.** MethodHandles có sửa bytecode method gốc không? **Không**.

**31.** `lookup.findStatic` type sai có thể ném gì? **NoSuchMethodException**.

**32.** `lookup()` có quyền mọi private class không? **Không**.

**33.** MethodHandle có tự bảo đảm thread safety cho target không? **Không**.

**34.** MethodHandles có luôn nhanh hơn direct Java method không? **Không có bảo đảm**.

**35.** Khi muốn catch cả parser và target exceptions nên đặt catch ở ngoài hay trong filter? **Bọc ngoài toàn bộ chain**.

**36.** `countedLoop` và `tryFinally` là API Java 7 gốc? **Không, bổ sung Java 9, hiện có trên Java 17**.

**37.** Khi nào nên dùng các combinators? **Runtime composition/type adaptation thực sự cần, không chỉ để thay method Java thông thường**.

## 44. Checklist production và Java 17

- [ ] Chọn target và `MethodType` chính xác.
- [ ] `Lookup` có quyền hợp lệ; không mở private JDK internals trái policy.
- [ ] Viết type trước/sau mỗi combinator.
- [ ] `filterArguments` unary filter có type phù hợp.
- [ ] `filterReturnValue` nhận đúng output target.
- [ ] `insertArguments` dùng vị trí trên **type hiện tại**.
- [ ] `dropArguments` chỉ dùng khi muốn bỏ qua incoming values.
- [ ] `permuteArguments` index/type hợp lệ, test semantic reorder.
- [ ] `guardWithTest` predicate boolean, branches cùng type.
- [ ] `catchException` chỉ bắt nhóm lỗi được policy cho phép.
- [ ] `foldArguments`/`collectArguments` không nhầm layout.
- [ ] `asCollector/asSpreader` có array/count đúng.
- [ ] `asType` conversion hợp lệ, không tự parse String.
- [ ] `explicitCastArguments` kiểm data loss.
- [ ] `invokeExact` khớp argument/return types của call site.
- [ ] `tryFinally` cleanup đúng signature và không che lỗi gốc.
- [ ] `countedLoop` có input/loop types và count rõ.
- [ ] Target/receiver/filters có thread-safety/ownership policy.
- [ ] Không cấp privileged handles cho callers không tin cậy.
- [ ] Không dùng MethodHandle thay authentication/business validation.
- [ ] Unit tests chạy happy path, wrong type, exceptions, boundaries.
- [ ] Benchmark thật nếu performance là lý do chọn approach.
- [ ] Không lạm dụng generic invokeWithArguments ở hot path.
- [ ] Code biên dịch và chạy trên Java 17+.
- [ ] Không gọi APIs legacy hoặc JDK internal hacks.

## 45. Tài liệu tham khảo Java SE 17

- [`MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): `type`, `invoke`, `invokeExact`, `asType`, `asCollector`, `asSpreader`, `bindTo`.
- [`MethodHandles`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): `filterArguments`, `filterReturnValue`, `insertArguments`, `dropArguments`, `permuteArguments`, `guardWithTest`, `catchException`, `foldArguments`, `collectArguments`, `countedLoop`, `tryFinally`, `explicitCastArguments`.
- [`MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html): exact method signature.
- [`MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `findStatic`, `findVirtual`, access rights.
- [`WrongMethodTypeException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/WrongMethodTypeException.html): type adaptation/invocation errors.
- [`Throwable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): exception propagation và cleanup.

**Tổng kết:** Sức mạnh của `MethodHandles` là **lắp ghép hành vi có kiểu**: biến đổi đầu vào/đầu ra, chọn nhánh, bắt lỗi, đặt tham số cố định, đổi thứ tự, truyền arrays và tạo control flow mà không sửa method gốc. Hãy theo dõi `MethodType` tại mỗi bước và hiểu ranh giới giữa conversion hợp lệ, lỗi kiểu, exception nghiệp vụ, quyền lookup và side effects. Các combinators là công cụ rất hữu ích cho runtime adapters/frameworks, không phải lý do để thay mọi phương thức Java thông thường.