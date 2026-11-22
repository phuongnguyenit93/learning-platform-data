# Phaser phân tầng khi số bên tham gia lớn — Java Concurrent

## 1. Bối cảnh: một barrier cho quá nhiều bên tham gia

Một bài toán song song lặp theo từng vòng (phase) thường yêu cầu: **mọi worker của vòng hiện tại phải hoàn thành trước khi bất kỳ worker nào bắt đầu vòng tiếp theo**. Ví dụ là mô phỏng vật lý, xử lý nhiều partitions, batch aggregation hay một pipeline có đồng bộ theo bước.

`java.util.concurrent.Phaser` là **reusable synchronization barrier** có thể thêm và bớt số bên tham gia (*parties*) khi chạy. Đây là API từ **Java 7** vẫn được hỗ trợ trên JDK hiện hành. Khi hàng trăm hoặc hàng nghìn participants cập nhật cùng một Phaser, áp lực cạnh tranh trên bộ đếm có thể trở nên đáng kể. Javadoc cho phép tổ chức **tiered phasers**: nhiều child Phasers gom những nhóm nhỏ, cùng phối hợp qua parent/root.

~~~text
PHẲNG
 Root Phaser (1 coordinator + 12 worker parties)
   / / / / / / / / / / / /
  12 workers cùng đồng bộ tại root

PHÂN TẦNG
           Root Phaser
      (1 coordinator + 4 children)
         /      |      \      \
      Group 0 Group 1 Group 2 Group 3
       / | \    / | \   / | \   / | \
     3 workers mỗi nhóm = 12 workers logic

Root chỉ nhìn thấy mỗi child đang hoạt động là một party.
~~~

Phân tầng **có thể giảm contention** và tăng throughput khi có nhiều parties đồng bộ rất thường xuyên, nhưng đồng thời làm tăng chi phí mỗi operation và độ phức tạp vòng đời. Nó **không tự động nhanh hơn** mọi Phaser phẳng, và cũng không tạo thêm CPU threads.

**Mục tiêu:** hiểu chính xác parent–child registration, arrival propagation, global phase advance, callback tại root, nhóm thay đổi thành viên, timeout, termination, giới hạn party và cách thiết kế/kiểm thử/đo hiệu năng đáng tin cậy.

**Phiên bản:** Các ví dụ Java đầy đủ bên dưới dùng API còn được hỗ trợ, tương thích **JDK 17+** và đã được biên dịch bằng `javac -encoding UTF-8 --release 17`, chạy trên JDK 17. Tài liệu đối chiếu Oracle Java SE 17/25. Phần thử nghiệm có 13 class độc lập, mỗi class là một chương trình riêng.

## 2. Một party trong Phaser có nghĩa gì?

`Phaser` quản lý **số lượt tham gia logic**, không giữ danh tính thread. Một party không nhất thiết tương đương một platform thread:

- `getRegisteredParties()` trả số parties **đăng ký tại chính Phaser được hỏi**.
- `getArrivedParties()` là số đã arrival ở pha đang xét.
- `getUnarrivedParties()` là số chưa arrival ở pha hiện tại.
- Các giá trị là **snapshot** có thể thay đổi trong lúc đọc; không dùng chúng để thay thế lời gọi đồng bộ.
- Một party phải báo arrival **đúng một lần mỗi phase** nếu vẫn registered.
- Phasers không ghi sổ danh tính party; gọi `arrive` trùng là misuse có thể không bị phát hiện ngay.
- `getPhase()` ban đầu thường là `0`, tăng khi toàn bộ parties đến barrier, có thể âm sau termination.

### 2.1. API cốt lõi

| Phương thức/constructor | Ý nghĩa |
| --- | --- |
| `new Phaser()` | Root chưa đăng ký party nào |
| `new Phaser(1)` | Root có coordinator party |
| `new Phaser(parent)` | Child với 0 party ban đầu |
| `new Phaser(parent, n)` | Child với n parties; nếu n lớn hơn 0, parent tự nhận một registration |
| `register()`, `bulkRegister(n)` | Đăng ký thêm parties |
| `arrive()` | Ghi nhận arrival **không chờ** |
| `arriveAndAwaitAdvance()` | Ghi nhận arrival và chờ phase advance |
| `arriveAndDeregister()` | Ghi nhận arrival và rút party khỏi các phase sau |
| `awaitAdvance(phase)` | Chờ phase đổi, **không** báo arrival |
| `awaitAdvanceInterruptibly(phase, timeout, unit)` | Chờ có timeout và interrupt |
| `getParent()`, `getRoot()` | Lấy parent trực tiếp và root của cây |
| `onAdvance(phase, parties)` | Callback ở **root** khi cây tiến phase, có thể quyết định termination |
| `forceTermination()` | Terminate toàn bộ cây để release waiting parties |

`arrive()` và `arriveAndDeregister()` không đợi các parties khác. Ngược lại `arriveAndAwaitAdvance()` có thể chặn thread cho tới khi toàn bộ cây đủ arrivals và **không có đối số timeout**.

### 2.2. Quy tắc automatic registration ở cây

Đây là cơ chế quan trọng nhất:

1. Child `new Phaser(parent,0)` **chưa** chiếm party ở parent.
2. Child chuyển từ 0 lên số parties dương bằng constructor/`register()`/`bulkRegister(n>0)` thì **parent tăng đúng một**.
3. Child đã có nhiều parties nhưng còn ít nhất một, parent vẫn chỉ tính child là **một party**.
4. Child dùng `arriveAndDeregister()` làm số parties về 0 thì **parent tự deregister một party**.
5. Trên cây nhiều tầng, một intermediate Phaser trở thành 0 parties cũng tự deregister lên ancestor.
6. Parent không cần và không nên tự `register()` lại một child vốn đã tự đăng ký theo constructor.

~~~text
Root(1) — child A(3), child B(2)

Root registered = 1 coordinator + 1(A) + 1(B) = 3
A registered    = 3
B registered    = 2

A giảm 3 -> 2 -> 1: root vẫn 3
A giảm 1 -> 0: root giảm xuống 2
B giảm 2 -> 1: root vẫn 2
B giảm 1 -> 0: root giảm xuống 1
Root coordinator rời đi: root có 0 parties
~~~

### 2.3. Vì sao phase ở root điều phối cả cây?

Worker gọi arrival ở **child**, không tự gọi ở root. Khi đủ parties trong child đến pha, child **đóng góp một arrival tới parent**. Parent chỉ advance khi đủ các parties của nó: các child hoạt động và coordinator (nếu có). Việc phase chung advance giải phóng các workers chờ ở children. Một child không có quyền tiến phase toàn cục riêng nếu root chưa đủ arrivals.

**Bẫy phổ biến:** Nếu đã đăng ký một coordinator party ở root, coordinator phải arrival mỗi phase, hoặc tự deregister theo giao thức phù hợp. Quên coordinator arrival làm mọi worker phải chờ, dù từng child đã đủ.

## 3. Lưu ý về concurrency, ownership và vòng đời

- **Registration không tạo thread.** `bulkRegister(500)` chỉ thay bộ đếm; ứng dụng phải có đủ tác vụ/phần việc chịu trách nhiệm arrivals.
- **Không tự động nhận diện party.** Phải gắn party ownership với worker/job rõ ràng; tránh double-arrive hay quên arrive.
- **Không gọi arrival trực tiếp ở parent thay cho child** theo thói quen; parent-child forwarding được thực hiện tự động.
- **Child rỗng biến mất khỏi parent count**, nên parent không chờ một nhóm đã rút hết trong pha sau.
- **Root mặc định có thể terminate khi về 0 parties**. Nếu cần nhóm rỗng rồi hoạt động lại, giữ coordinator tại root hoặc chủ động override chính sách root.
- **Không chạy tác vụ gây blocking kéo dài trong `onAdvance`**, và không gọi arrival/register/waiting trên chính Phaser từ callback (Javadoc nêu hiệu ứng không được bảo đảm).
- **Phaser không tự cancel công việc bên ngoài.** `forceTermination()` không shutdown ExecutorService hay đóng tài nguyên.
- **Fixed-size thread pool** với ít threads hơn tổng số workers cần chờ có thể gây starvation; workers bị chặn chiếm hết threads trong khi các tasks chưa chạy cũng cần đến barrier.

## 4. Bộ ví dụ chạy độc lập

Mỗi ví dụ là một class Java hoàn chỉnh. Nếu copy vào thư mục học tập, lưu thành đúng tên file trong tiêu đề, chạy bằng hai lệnh đi kèm. Các test một-thread được dùng **để kiểm chứng bộ đếm cấu trúc**, không phải giả làm benchmark concurrent. Những test đa luồng có timeout và termination recovery để tránh treo khi xảy ra lỗi.
## 5. Ví dụ 1 — Parent đếm child đang hoạt động, không đếm mọi worker

Root có coordinator và hai child lần lượt gồm 3 và 2 parties. Khi từng child rỗng, root tự giảm một party. Đây là kiểm thử cơ bản nhất chống lỗi tự register parent hai lần.

Tạo file `ParentChildCountsDemo.java`:

~~~java
import java.util.concurrent.*;
public class ParentChildCountsDemo {
 public static void main(String[] args) {
  Phaser root=new Phaser(1);
  Phaser east=new Phaser(root,3),west=new Phaser(root,2);
  System.out.println("rootParties="+root.getRegisteredParties());
  System.out.println("eastParties="+east.getRegisteredParties());
  System.out.println("westParties="+west.getRegisteredParties());
  System.out.println("eastParentIsRoot="+(east.getParent()==root));
  System.out.println("westRootIsRoot="+(west.getRoot()==root));
  System.out.println("initialPhase="+root.getPhase());
  for(int i=0;i<3;i++)east.arriveAndDeregister();
  System.out.println("rootAfterEast="+root.getRegisteredParties());
  for(int i=0;i<2;i++)west.arriveAndDeregister();
  System.out.println("rootAfterWest="+root.getRegisteredParties());
  root.arriveAndDeregister();
  System.out.println("rootTerminated="+root.isTerminated());
 }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 --release 17 ParentChildCountsDemo.java
java ParentChildCountsDemo
~~~

Stdout đã kiểm chứng:

~~~text
rootParties=3
eastParties=3
westParties=2
eastParentIsRoot=true
westRootIsRoot=true
initialPhase=0
rootAfterEast=2
rootAfterWest=1
rootTerminated=true
~~~

**Giải thích:** Gọi `east.arriveAndDeregister()` ba lần thay cho ba parties logic, không tạo ba threads. Root ban đầu 3, sau khi child A rỗng còn 2; child B rỗng còn 1; coordinator cuối cùng deregister khiến root terminated theo chính sách mặc định.

## 6. Ví dụ 2 — Child rỗng, bulkRegister rồi tự deregister khỏi parent

Kiểm thử đúng sự kiện chuyển 0→n và n→0, cũng như việc child có thể register trở lại khi root vẫn chưa terminated.

Tạo file `LazyChildRegistrationDemo.java`:

~~~java
import java.util.concurrent.*;
public class LazyChildRegistrationDemo {
 public static void main(String[] args){
  Phaser root=new Phaser(1),child=new Phaser(root,0);
  System.out.println("rootInitially="+root.getRegisteredParties());
  System.out.println("childInitially="+child.getRegisteredParties());
  child.bulkRegister(2);
  System.out.println("rootAfterBulk="+root.getRegisteredParties());
  System.out.println("childAfterBulk="+child.getRegisteredParties());
  child.arriveAndDeregister();
  System.out.println("rootAfterFirstDeparture="+root.getRegisteredParties());
  child.arriveAndDeregister();
  System.out.println("rootAfterEmpty="+root.getRegisteredParties());
  child.register();
  System.out.println("rootAfterRevive="+root.getRegisteredParties());
  child.arriveAndDeregister();
  root.arriveAndDeregister();
  System.out.println("terminated="+root.isTerminated());
 }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 --release 17 LazyChildRegistrationDemo.java
java LazyChildRegistrationDemo
~~~

Stdout đã kiểm chứng:

~~~text
rootInitially=1
childInitially=0
rootAfterBulk=2
childAfterBulk=2
rootAfterFirstDeparture=2
rootAfterEmpty=1
rootAfterRevive=2
terminated=true
~~~

**Giải thích:** Khi child có 2 parties, root vẫn chỉ thêm một. Một party rút đi nhưng child còn 1 thì root vẫn 2; party cuối rút thì root trở về 1. `child.register()` tiếp theo làm root trở về 2 vì root còn coordinator đang hoạt động.

## 7. Ví dụ 3 — Cây ba tầng: root → region → team

Đây là ví dụ phân tầng nhiều cấp, trong đó hai region Phasers chỉ mang một party đại diện của mỗi leaf. Kiểm tra `getRoot()` trả ancestor ngoài cùng.

Tạo file `ThreeLevelTreeDemo.java`:

~~~java
import java.util.concurrent.*;
public class ThreeLevelTreeDemo {
 public static void main(String[] args) {
  Phaser root=new Phaser(1);
  Phaser regionA=new Phaser(root,0),regionB=new Phaser(root,0);
  Phaser teamA=new Phaser(regionA,4),teamB=new Phaser(regionB,4);
  System.out.println("rootParties="+root.getRegisteredParties());
  System.out.println("regionAParties="+regionA.getRegisteredParties());
  System.out.println("regionBParties="+regionB.getRegisteredParties());
  System.out.println("teamAParties="+teamA.getRegisteredParties());
  System.out.println("teamBParties="+teamB.getRegisteredParties());
  System.out.println("teamBRootIsRoot="+(teamB.getRoot()==root));
  for(int i=0;i<4;i++){teamA.arriveAndDeregister();teamB.arriveAndDeregister();}
  System.out.println("rootAfterLeavesGone="+root.getRegisteredParties());
  root.arriveAndDeregister();
  System.out.println("rootTerminated="+root.isTerminated());
 }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 --release 17 ThreeLevelTreeDemo.java
java ThreeLevelTreeDemo
~~~

Stdout đã kiểm chứng:

~~~text
rootParties=3
regionAParties=1
regionBParties=1
teamAParties=4
teamBParties=4
teamBRootIsRoot=true
rootAfterLeavesGone=1
rootTerminated=true
~~~

**Giải thích:** Root là coordinator 1 + hai regions. Mỗi region chỉ có một party do team bên dưới đại diện, không phải bốn. Khi các teams rút hết, đăng ký được rút theo chuỗi lên root.

## 8. Ví dụ 4 — Sáu worker thực, hai nhóm và ba pha đồng bộ

Đây là ví dụ dùng threads thật: root(1), hai child(3), fixed executor 6 threads, ba vòng. Coordinator dùng `arrive()` và `awaitAdvanceInterruptibly(...,10,SECONDS)` để có timeout; `Future.get` kiểm tra workers hoàn tất, và `finally` forceTerminate/shutdownNow khi cần.

Tạo file `TwoRoundsTieredDemo.java`:

~~~java
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
public class TwoRoundsTieredDemo{
 public static void main(String[] args)throws Exception{
  final int workers=6,rounds=3;
  Phaser root=new Phaser(1);
  Phaser[] groups={new Phaser(root,3),new Phaser(root,3)};
  AtomicIntegerArray completed=new AtomicIntegerArray(rounds);
  ExecutorService exec=Executors.newFixedThreadPool(workers);
  List<Future<?>> futures=new ArrayList<>();
  try{
   for(int id=0;id<workers;id++){
    final Phaser local=groups[id/3];
    futures.add(exec.submit(()->{
     try{
      for(int phase=0;phase<rounds;phase++){
       completed.incrementAndGet(phase);
       int next=local.arriveAndAwaitAdvance();
       if(next<0)throw new IllegalStateException("terminated early");
      }
     }finally{local.arriveAndDeregister();}
    }));
   }
   for(int i=0;i<rounds;i++){
    int previous=root.arrive();
    int next=root.awaitAdvanceInterruptibly(previous,10,TimeUnit.SECONDS);
    if(next<0)throw new IllegalStateException("terminated unexpectedly");
    System.out.println("phase="+next+" completed="+completed.get(i));
   }
   for(Future<?> f:futures)f.get(10,TimeUnit.SECONDS);
   System.out.println("parentPartiesAfter="+root.getRegisteredParties());
   root.arriveAndDeregister();
   System.out.println("terminated="+root.isTerminated());
  }finally{
   root.forceTermination();
   exec.shutdownNow();
   exec.awaitTermination(2,TimeUnit.SECONDS);
  }
 }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 --release 17 TwoRoundsTieredDemo.java
java TwoRoundsTieredDemo
~~~

Stdout đã kiểm chứng:

~~~text
phase=1 completed=6
phase=2 completed=6
phase=3 completed=6
parentPartiesAfter=1
terminated=true
~~~

**Giải thích:** Mỗi worker tăng bộ đếm của vòng trước arrival. Root chỉ advance khi mọi child đã hoàn thành, nhờ vậy main thấy đúng sáu lượt hoàn tất mỗi pha. `arriveAndAwaitAdvance()` không có timeout; vì thế coordinator tách arrival và `awaitAdvanceInterruptibly`. Các workers `arriveAndDeregister()` khi hết ba vòng, root trở về một party coordinator. Quan trọng: fixed pool quá ít threads có thể bị starvation nếu mọi workers đang đợi các tasks chưa được chạy.

## 9. Ví dụ 5 — Trong cây, onAdvance chạy ở root chứ không ở child

Dùng AtomicInteger để đếm callback: mặc dù child override `onAdvance`, trong tiered set chỉ root callback chạy khi toàn cây advance. Root kết thúc sau vòng thứ hai.

Tạo file `RootOnAdvanceDemo.java`:

~~~java
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
public class RootOnAdvanceDemo{
 public static void main(String[] args) {
  AtomicInteger rootCallbacks=new AtomicInteger(),childCallbacks=new AtomicInteger();
  Phaser root=new Phaser(1){
   @Override protected boolean onAdvance(int phase,int parties){
    rootCallbacks.incrementAndGet();return phase>=1||parties==0;
   }
  };
  Phaser child=new Phaser(root,1){
   @Override protected boolean onAdvance(int phase,int parties){
    childCallbacks.incrementAndGet();return false;
   }
  };
  for(int i=0;i<2;i++){root.arrive();child.arriveAndAwaitAdvance();}
  System.out.println("rootCallbacks="+rootCallbacks.get());
  System.out.println("childCallbacks="+childCallbacks.get());
  System.out.println("rootTerminated="+root.isTerminated());
  System.out.println("childTerminated="+child.isTerminated());
 }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 --release 17 RootOnAdvanceDemo.java
java RootOnAdvanceDemo
~~~

Stdout đã kiểm chứng:

~~~text
rootCallbacks=2
childCallbacks=0
rootTerminated=true
childTerminated=true
~~~

**Giải thích:** Đây là bài test một thread cho semantics callback, không phải đo throughput. Root callback trả true khi phase>=1 và toàn cây terminated; các lời gọi chờ sau termination trả phase âm. Không gọi registration/arrival/waiting của chính Phaser trong `onAdvance`: Javadoc quy định hiệu ứng không xác định.

## 10. Ví dụ 6 — forceTermination lan ra toàn cây nhưng không xóa party counts

Phân biệt termination của barrier với cleanup của các resources và đăng ký logic.

Tạo file `ForceTerminationDemo.java`:

~~~java
import java.util.concurrent.*;
public class ForceTerminationDemo{
 public static void main(String[] args){
  Phaser root=new Phaser(1),child=new Phaser(root,2);
  System.out.println("rootPartiesBefore="+root.getRegisteredParties());
  root.forceTermination();
  System.out.println("rootTerminated="+root.isTerminated());
  System.out.println("childTerminated="+child.isTerminated());
  System.out.println("registrationNegative="+(child.register()<0));
  System.out.println("awaitReturnsNegative="+(child.arriveAndAwaitAdvance()<0));
  System.out.println("rootPartiesAfter="+root.getRegisteredParties());
  System.out.println("childPartiesAfter="+child.getRegisteredParties());
 }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 --release 17 ForceTerminationDemo.java
java ForceTerminationDemo
~~~

Stdout đã kiểm chứng:

~~~text
rootPartiesBefore=2
rootTerminated=true
childTerminated=true
registrationNegative=true
awaitReturnsNegative=true
rootPartiesAfter=2
childPartiesAfter=2
~~~

**Giải thích:** Root và child đều terminated, nhưng party counts vẫn 2 và 2. `forceTermination()` không cancel threads, không shutdown ExecutorService, không xóa counters hay rollback công việc. Trên Phaser terminated, `register` không làm sống lại cây và trả kết quả âm.

## 11. Ví dụ 7 — Timeout không tự động deregister party

Mô phỏng child đã arrive nhưng coordinator chưa arrive: `awaitAdvanceInterruptibly` timeout rồi chủ động terminate toàn cây. Không gọi `arriveAndDeregister` lần hai cho cùng party trong cùng phase để cố sửa lỗi.

Tạo file `TimedWaitRecoveryDemo.java`:

~~~java
import java.util.concurrent.*;
public class TimedWaitRecoveryDemo{
 public static void main(String[] args)throws Exception{
  Phaser root=new Phaser(1),child=new Phaser(root,1);
  int arrived=child.arrive();
  boolean timedOut=false;
  try{child.awaitAdvanceInterruptibly(arrived,100,TimeUnit.MILLISECONDS);}
  catch(TimeoutException e){timedOut=true;}
  System.out.println("timedOut="+timedOut);
  System.out.println("rootRegisteredAfterTimeout="+root.getRegisteredParties());
  System.out.println("rootUnarrivedAfterTimeout="+root.getUnarrivedParties());
  root.forceTermination();
  System.out.println("rootTerminated="+root.isTerminated());
  System.out.println("childTerminated="+child.isTerminated());
 }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 --release 17 TimedWaitRecoveryDemo.java
java TimedWaitRecoveryDemo
~~~

Stdout đã kiểm chứng:

~~~text
timedOut=true
rootRegisteredAfterTimeout=2
rootUnarrivedAfterTimeout=1
rootTerminated=true
childTerminated=true
~~~

**Giải thích:** Timeout xảy ra vì root coordinator vẫn là party chưa arrival. Parent còn 2 registered parties, một đã arrived (child) và một chưa (coordinator). Timeout không làm giảm registrations; muốn phục hồi, cần policy rõ, ví dụ forceTerminate và cleanup tasks.

## 12. Ví dụ 8 — Cùng 12 workers logic: flat root 13 parties, tiered root 5 parties

Đối chiếu cấu trúc đếm của flat Phaser với 4 child groups có 3 parties mỗi nhóm. Phép thử này là đếm registrations tuần tự, không phải benchmark contention.

Tạo file `FlatVsTieredCountsDemo.java`:

~~~java
import java.util.concurrent.*;
public class FlatVsTieredCountsDemo{
 public static void main(String[] args){
  Phaser flat=new Phaser(13);
  Phaser root=new Phaser(1);
  Phaser[] groups=new Phaser[4];
  for(int i=0;i<4;i++)groups[i]=new Phaser(root,3);
  System.out.println("flatPartiesInitially="+flat.getRegisteredParties());
  System.out.println("tieredRootPartiesInitially="+root.getRegisteredParties());
  int sum=0;for(Phaser g:groups)sum+=g.getRegisteredParties();
  System.out.println("totalChildParties="+sum);
  for(int i=0;i<12;i++){flat.arriveAndDeregister();groups[i/3].arriveAndDeregister();}
  System.out.println("flatPartiesAfterWorkers="+flat.getRegisteredParties());
  System.out.println("rootPartiesAfterWorkers="+root.getRegisteredParties());
  flat.arriveAndDeregister();root.arriveAndDeregister();
  System.out.println("bothTerminated="+(flat.isTerminated()&&root.isTerminated()));
 }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 --release 17 FlatVsTieredCountsDemo.java
java FlatVsTieredCountsDemo
~~~

Stdout đã kiểm chứng:

~~~text
flatPartiesInitially=13
tieredRootPartiesInitially=5
totalChildParties=12
flatPartiesAfterWorkers=1
rootPartiesAfterWorkers=1
bothTerminated=true
~~~

**Giải thích:** Root của cây chỉ giữ 1 coordinator + 4 child = 5 parties, dù tổng 12 workers logic tại leaves. Không thể suy ra tree nhanh hơn từ hai con số 13 và 5: muốn đánh giá throughput phải có nhiều threads, pha lặp và phép đo công bằng.

## 13. Ví dụ 9 — 16.000 parties logic phân thành 32 child Phasers

Cho thấy tổng registrations của cây có thể lớn mà mỗi node vẫn dưới giới hạn. Chương trình **không** tạo 16.000 threads: chỉ register và deregister 16.000 lượt logic.

Tạo file `LargeHierarchyCountsDemo.java`:

~~~java
import java.util.concurrent.*;
public class LargeHierarchyCountsDemo{
 public static void main(String[] args){
  final int groups=32,perGroup=500;
  Phaser root=new Phaser(1);
  Phaser[] children=new Phaser[groups];
  for(int i=0;i<groups;i++)children[i]=new Phaser(root,perGroup);
  System.out.println("groups="+groups);
  System.out.println("logicalParties="+(groups*perGroup));
  System.out.println("rootPartiesWithCoordinator="+root.getRegisteredParties());
  System.out.println("partiesPerChild="+children[0].getRegisteredParties());
  for(Phaser child:children)for(int j=0;j<perGroup;j++)child.arriveAndDeregister();
  System.out.println("rootAfterChildDepartures="+root.getRegisteredParties());
  root.arriveAndDeregister();
  System.out.println("terminated="+root.isTerminated());
 }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 --release 17 LargeHierarchyCountsDemo.java
java LargeHierarchyCountsDemo
~~~

Stdout đã kiểm chứng:

~~~text
groups=32
logicalParties=16000
rootPartiesWithCoordinator=33
partiesPerChild=500
rootAfterChildDepartures=1
terminated=true
~~~

**Giải thích:** Root ban đầu có 33 parties (32 nhóm + coordinator), mỗi child có 500, tổng logic 16.000. Chia cây giảm số parties trên một node nhưng **không** tạo thêm CPU, không tự thực thi 16.000 tasks và không bảo đảm có đủ RAM/threads.

## 14. Ví dụ 10 — Giới hạn per-Phaser và tham số âm

Implementation JDK được Javadoc mô tả giới hạn **65.535 parties trên mỗi Phaser**. Constructor quá giới hạn/giá trị âm ném IllegalArgumentException; khi register vượt max từ một trạng thái có sẵn có thể ném IllegalStateException.

Tạo file `ValidationCapDemo.java`:

~~~java
import java.util.concurrent.*;
public class ValidationCapDemo {
 public static void main(String[] args){
  boolean tooMany=false,negative=false,negativeChild=false,negativeBulk=false;
  try{new Phaser(65536);}catch(IllegalArgumentException e){tooMany=true;}
  try{new Phaser(-1);}catch(IllegalArgumentException e){negative=true;}
  Phaser root=new Phaser(1);
  try{new Phaser(root,-1);}catch(IllegalArgumentException e){negativeChild=true;}
  Phaser child=new Phaser(root,0);
  try{child.bulkRegister(-1);}catch(IllegalArgumentException e){negativeBulk=true;}
  System.out.println("maxPartiesRejected="+tooMany);
  System.out.println("negativeRootRejected="+negative);
  System.out.println("negativeChildRejected="+negativeChild);
  System.out.println("negativeBulkRejected="+negativeBulk);
  System.out.println("rootStillOne="+(root.getRegisteredParties()==1));
  root.arriveAndDeregister();
 }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 --release 17 ValidationCapDemo.java
java ValidationCapDemo
~~~

Stdout đã kiểm chứng:

~~~text
maxPartiesRejected=true
negativeRootRejected=true
negativeChildRejected=true
negativeBulkRejected=true
rootStillOne=true
~~~

**Giải thích:** Giới hạn 65.535 là **trên mỗi Phaser**, không phải giới hạn threads của JVM và cũng không phải tổng registrations tối đa toàn cây. Không lấy input không tin cậy để đăng ký số lượng khổng lồ mà không có ngân sách bộ nhớ/CPU.

## 15. Ví dụ 11 — Memory visibility sau phase advance qua parent

Hai workers ghi vào hai index riêng rồi arrive ở child; coordinator root chỉ đọc sau khi phase advance. Điều này minh họa happens-before do barrier đảm bảo, kết hợp với không ghi chồng vùng.

Tạo file `VisibilityTieredDemo.java`:

~~~java
import java.util.*;
import java.util.concurrent.*;
public class VisibilityTieredDemo{
 public static void main(String[] args)throws Exception{
  Phaser root=new Phaser(1),child=new Phaser(root,2);
  int[] values=new int[2];
  ExecutorService exec=Executors.newFixedThreadPool(2);
  List<Future<?>> futures=new ArrayList<>();
  try{
   for(int id=0;id<2;id++){
    final int slot=id;
    futures.add(exec.submit(()->{
     values[slot]=10+slot;
     child.arriveAndAwaitAdvance();
     child.arriveAndDeregister();
    }));
   }
   int prior=root.arrive();
   int next=root.awaitAdvanceInterruptibly(prior,10,TimeUnit.SECONDS);
   System.out.println("phaseAdvanced="+(next>prior));
   System.out.println("sumAfterBarrier="+(values[0]+values[1]));
   for(Future<?> f:futures)f.get(10,TimeUnit.SECONDS);
   System.out.println("rootAfterWorkers="+root.getRegisteredParties());
   root.arriveAndDeregister();
   System.out.println("rootTerminated="+root.isTerminated());
  }finally{
   root.forceTermination();exec.shutdownNow();exec.awaitTermination(2,TimeUnit.SECONDS);
  }
 }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 --release 17 VisibilityTieredDemo.java
java VisibilityTieredDemo
~~~

Stdout đã kiểm chứng:

~~~text
phaseAdvanced=true
sumAfterBarrier=21
rootAfterWorkers=1
rootTerminated=true
~~~

**Giải thích:** Các writes `values[0]=10` và `values[1]=11` xảy ra trước arrival. Root advance thiết lập happens-before để coordinator thấy dữ liệu sau barrier. Không suy rộng thành việc mảng thông thường thread-safe nếu workers ghi cùng index đồng thời.

## 16. Ví dụ 12 — Một nhóm rút sau phase đầu, nhóm còn lại tiếp tục

Sau khi right về 0 parties, root không phải chờ right ở phase sau. Coordinator/root vẫn phải arrival mỗi phase, left còn số parties hợp lệ.

Tạo file `DynamicDeregisterDemo.java`:

~~~java
import java.util.concurrent.*;
public class DynamicDeregisterDemo{
 public static void main(String[] args){
  Phaser root=new Phaser(1),left=new Phaser(root,2),right=new Phaser(root,1);
  root.arrive();
  left.arrive();
  right.arriveAndDeregister();
  int phase1=left.arriveAndAwaitAdvance();
  System.out.println("phaseAfterFirstRound="+phase1);
  System.out.println("rootAfterRightDeparts="+root.getRegisteredParties());
  root.arrive();
  left.arrive();
  left.arriveAndDeregister();
  System.out.println("phaseAfterSecondRound="+root.getPhase());
  System.out.println("leftPartiesNow="+left.getRegisteredParties());
  left.arriveAndDeregister();
  root.arriveAndDeregister();
  System.out.println("terminated="+root.isTerminated());
 }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 --release 17 DynamicDeregisterDemo.java
java DynamicDeregisterDemo
~~~

Stdout đã kiểm chứng:

~~~text
phaseAfterFirstRound=1
rootAfterRightDeparts=2
phaseAfterSecondRound=2
leftPartiesNow=1
terminated=true
~~~

**Giải thích:** Dữ liệu: phase 0 có left và right; right rời đi và root giảm còn 2 (coordinator + left). Phase 1 chỉ còn left; sau đó một party left còn đăng ký cho phase 2 trước khi cleanup. Đây là test logic single-thread để tránh nondeterministic logging.

## 17. Ví dụ 13 — Root giữ hoạt động sau khi tổng parties về 0

Mặc định root terminate khi về 0 parties lúc advance. Nếu cần giữ cây có thể đăng ký lại khi rỗng, override `onAdvance` tại root trả false và terminate chủ động theo vòng đời service.

Tạo file `StableRootDemo.java`:

~~~java
import java.util.concurrent.*;
public class StableRootDemo{
 public static void main(String[] args){
  Phaser root=new Phaser(0){
   @Override protected boolean onAdvance(int phase,int parties){return false;}
  };
  Phaser child=new Phaser(root,1);
  child.arriveAndDeregister();
  System.out.println("phaseAfterFirstDeparture="+root.getPhase());
  System.out.println("terminatedAfterZero="+root.isTerminated());
  child.register();
  System.out.println("rootAfterRevival="+root.getRegisteredParties());
  child.arriveAndDeregister();
  System.out.println("phaseAfterSecondDeparture="+root.getPhase());
  System.out.println("stillActive="+!root.isTerminated());
  root.forceTermination();
  System.out.println("terminatedOnDemand="+root.isTerminated());
 }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 --release 17 StableRootDemo.java
java StableRootDemo
~~~

Stdout đã kiểm chứng:

~~~text
phaseAfterFirstDeparture=1
terminatedAfterZero=false
rootAfterRevival=1
phaseAfterSecondDeparture=2
stillActive=true
terminatedOnDemand=true
~~~

**Giải thích:** Root về 0 vẫn không terminated do callback trả false, vì thế child có thể register lại và tự thêm party ở root. Sau khi service kết thúc cần `forceTermination()`; đừng giữ tree vô thời hạn chỉ để né quản lý lifecycle.


## 18. Những điểm chính khi diễn giải kết quả kiểm thử

Mười ba ví dụ chứng minh ba nhóm điều kiện riêng biệt:

- **Cấu trúc registration:** parent/child/three-level tree, lazy/bulk registration, flat-vs-tiered party counts, 16.000 parties logic và giới hạn per-node.
- **Đồng bộ pha thật:** ví dụ 6 worker/3 phase, visibility sau barrier và nhóm động rời đi.
- **Quản lý vòng đời và lỗi:** onAdvance tại root, timeout, forceTermination và root tái sử dụng sau zero party.

Không gộp các kết quả thành lời hứa rằng phân tầng nhanh hơn. Chỉ có phép đo contention/throughput riêng mới đánh giá được lợi ích hiệu năng.

## 19. Mô hình vận hành khuyến nghị

### 19.1. Chọn topology dựa trên workload, không theo cảm tính

Một cách tiếp cận có thể bảo trì:

1. Xác định **số participants logic** và số phase cần hoàn tất.
2. Chọn số worker threads/executor capacity thực tế.
3. Xây baseline bằng **một Phaser phẳng** nếu số bên ít.
4. Khi profiling xác nhận contention đáng kể, phân nhóm theo ownership/locality (CPU partitions, shards, regions).
5. Mỗi worker gọi synchronization trên **child của mình**, không trực tiếp ở root.
6. Trên parent, chỉ thêm coordinator party nếu coordinator sẽ arrive mỗi phase.
7. Đăng ký tất cả parties cần tham gia trước khi phase khởi chạy, hoặc áp dụng protocol đăng ký động rõ ràng.
8. Chọn group size và cây hai/ba tầng dựa trên benchmark.
9. Có timeout/recovery và caller xử lý exception.
10. Đóng cả tree lifecycle, shutdown executor, và kiểm tra rò rỉ resources.

### 19.2. Đừng đánh đồng số party với số luồng

`new Phaser(parent,500)` có nghĩa child đang đợi **500 arrival slots logic**; nó **không** tạo 500 threads. Nếu bạn chỉ chạy 10 tasks mà lại đăng ký 500 parties, barrier có thể chờ mãi vì thiếu 490 arrivals. Ngược lại, nếu mỗi thread phụ trách nhiều đơn vị công việc và có cách báo arrival đúng số lần, con số parties có thể khác số threads. Nhưng phương án này cần ownership chính xác để không double-arrive.

### 19.3. Chọn kích thước group

Javadoc `Phaser` gợi ý `TASKS_PER_PHASER` tùy tần suất synchronization: một group nhỏ cỡ **4** có thể phù hợp những phase cực ngắn và đồng bộ dày; khi mỗi phase làm nhiều việc có thể dùng **hàng trăm** parties per group. Đây là **heuristic**, không phải mặc định cho mọi CPU/JVM.

| Workload | Hướng tiếp cận |
| --- | --- |
| 8 workers, computation mỗi phase rất lâu | Phaser phẳng thường dễ hiểu |
| 256 workers, nhiều phase cực ngắn | Cân nhắc tiered sau khi đo contention |
| 16.000 logical participants | Chia groups để mỗi node dưới per-node cap; vẫn phải quản lý threads |
| Nhiều vùng địa lý/partition | Root → region → team khi ownership phù hợp |
| Một số nhóm thường rỗng | Child lazy registration, root policy có chủ đích |
| Workers có nguy cơ lỗi | Coordinator timeout, forceTermination và recovery rõ ràng |

### 19.4. Cấu trúc phase và memory consistency

Javadoc quy định actions trước arrival **happens-before** phase advance/onAdvance tương ứng và actions sau advance. Nên tổ chức mỗi phase:

~~~text
Worker:    cập nhật dữ liệu thuộc quyền sở hữu
Worker:    child.arriveAndAwaitAdvance()
Root:      đợi mọi child arrival + coordinator arrival
Root:      advance phase chung
Worker:    xử lý dữ liệu phase mới
~~~

Barrier không làm dữ liệu tự thread-safe nếu **trong cùng một phase** hai workers cùng ghi một biến thông thường mà không đồng bộ.

## 20. Timeout, interruption, termination và recovery

Các API wait không giống nhau:

| Lời gọi | Có arrival? | Có wait? | Hành vi |
| --- | --- | --- | --- |
| `arrive()` | Có | Không | Trả phase của arrival |
| `arriveAndDeregister()` | Có | Không | Party rút khỏi các phase tiếp |
| `arriveAndAwaitAdvance()` | Có | Có | Không có timeout parameter |
| `awaitAdvance(phase)` | Không | Có | Có thể đợi tiếp dù thread bị interrupt |
| `awaitAdvanceInterruptibly(phase)` | Không | Có | Interruptible |
| `awaitAdvanceInterruptibly(phase,timeout,unit)` | Không | Có | TimeoutException/InterruptedException |
| `forceTermination()` | Không | Không | Chuyển cả cây sang terminated, giải phóng waiters |

Nếu timeout:

- Không tự mặc định party đã bị deregister.
- Không gọi `arriveAndDeregister` lần hai cho cùng party vừa `arrive` trong phase đó.
- Xác định recovery ở cấp job; thường `root.forceTermination()`, sau đó dừng/cleanup workers.
- Kiểm tra các kết quả phase **âm** và không tiếp tục xử lý như một barrier advance bình thường.
- `forceTermination()` không tự cancel Future, không interrupt các thread đang chạy CPU/IO, không shutdown pool và không reset counts.
- Một cây đã terminated mặc định **không thể sống lại** chỉ bằng `register()`; cần tạo cây mới hoặc thiết kế root nonterminating từ đầu.

## 21. Giới hạn 65.535 parties được hiểu thế nào?

Javadoc mô tả implementation `Phaser` giới hạn tối đa **65.535** registered parties **ở mỗi node**. Constructor với số âm/quá giới hạn ném `IllegalArgumentException`; `register()`/`bulkRegister()` khi làm vượt số lượng tối đa từ trạng thái đang có có thể ném `IllegalStateException`.

Trong cây tiered:

- Mỗi leaf, intermediate và root có **giới hạn riêng**.
- Parent chỉ tính một party trên mỗi child đang nonempty.
- Tổng registrations logic trên **toàn cây** có thể vượt 65.535 nếu chia đúng.
- CPU cores, RAM, số threads, GC và scheduling vẫn có giới hạn thực.
- Đừng để input người dùng điều khiển số registrations tùy ý, dù cây hỗ trợ tổng lớn.

Không khẳng định “Phaser hỗ trợ vô hạn workers”, cũng không đánh đồng 65.535 với số threads tối đa của JVM.

## 22. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Child đã có parent nhưng lại `parent.register()` thủ công | Phantom party ở parent, gây treo | Chỉ register workers ở child |
| Root có coordinator party nhưng không arrival | Mọi groups có thể chờ mãi | Coordinator arrive mỗi phase hoặc không đăng ký làm party |
| `child(4)` nhưng chỉ ba parties thực sự arrive | Child không advance | Khớp đăng ký và ownership |
| Đếm `root.getRegisteredParties()` là tổng workers | Thống kê sai | Tự ghi nhận topology/leaf counts |
| Tạo child với zero rồi tin parent đã đăng ký | Root ít party hơn tưởng tượng | Parent chỉ tăng khi child nonempty |
| `arrive()` rồi `arriveAndDeregister()` cùng party trong cùng phase | Double-arrive, sai counts | Giao thức mỗi party một arrival mỗi phase |
| Timeout rồi nghĩ registration tự giảm | Lỗi recovery/barrier treo | ForceTermination/rebuild policy |
| Override `onAdvance` ở child | Callback không chạy | Đặt callback tại root |
| Chạy I/O chặn trong `onAdvance` | Waiters chờ lâu | Callback cực ngắn |
| Gọi lại register/await trên chính Phaser trong `onAdvance` | Semantics không xác định | Tránh thao tác lại trong callback |
| Phân tầng quá sâu khi chỉ có vài parties | Tăng overhead | Benchmark và đơn giản hóa |
| Fixed executor thiếu threads cho parties đang đợi | Starvation/deadlock | Bảo đảm worker execution capacity |
| Root tự terminate sau khi mọi child rỗng | Batch sau không register lại được | Root giữ coordinator hoặc onAdvance policy |
| `forceTermination` được coi là executor shutdown | Tasks vẫn chạy | Shutdown/cancel và đóng resource riêng |
| Dùng snapshots làm điều kiện synchronization | Race condition | Dùng arrival/await methods |
| Coi register 16k parties là 16k parallel threads | Lập kế hoạch tài nguyên sai | Parties là logic slots |

## 23. Benchmark phẳng so với phân tầng

Tài liệu Javadoc xác nhận tiering có thể tăng throughput khi synchronization contention lớn **nhưng phải trả thêm per-operation overhead**. Chỉ số có ý nghĩa:

| Metric | Cần diễn giải |
| --- | --- |
| Phases/second | Bao nhiêu vòng **toàn cục** hoàn tất mỗi giây |
| Arrival calls/second | Số calls, không phải số phases |
| Worker wait latency | Chờ các nhóm còn lại bao lâu |
| CPU usage | Contention, scheduling và công việc thực |
| Allocations/GC | Overhead task/Phaser objects |
| Group imbalance | Một child chậm tác động thế nào đến root |
| Timeout/failure rate | Đúng tính sẵn sàng, không chỉ throughput |

Quy trình benchmark:

1. Dùng **cùng số workers**, phases và công việc giữa phases cho flat/tiered.
2. Warm-up JVM; tránh tính cả khởi tạo threads vào một phía mà phía kia được reuse.
3. Thử nhiều workload sizes, group sizes và số tầng.
4. Ghi JDK/OS/CPU/GC/thread counts.
5. Không in log trong mỗi phase nếu muốn đo overhead barrier.
6. Đo nhiều lần, báo độ biến thiên thay vì một phép `System.nanoTime()` duy nhất.
7. Kiểm tra đúng **mọi worker hoàn tất từng phase** trước khi đo speedup.
8. Nếu dùng JMH, bảo đảm benchmark setup/barrier groups không tự tạo deadlock hoặc khác biệt ngoài ý muốn.

Đọc thêm [OpenJDK Java Microbenchmark Harness](https://github.com/openjdk/jmh). Mười ba chương trình trong bài là **kiểm thử tính đúng và lifecycle**, không phải kết quả benchmark throughput.

## 24. Checklist trước khi đưa vào hệ thống thật

- [ ] Root/region/team parent links được thiết lập đúng; mọi worker có một child owner rõ.
- [ ] Coordinator nếu là registered party thì có arrival mỗi phase.
- [ ] Child từ 0 lên n>0 tự tăng parent đúng một party; n về 0 tự giảm parent.
- [ ] Không register một child hai lần tại parent.
- [ ] Số party mỗi node không vượt giới hạn implementation.
- [ ] Parties logic và executor thread capacity được tính riêng.
- [ ] Không có thread pool starvation bởi tasks cùng chờ barrier.
- [ ] Từng phase có đủ arrivals, không double-arrive.
- [ ] `arriveAndAwaitAdvance`/`awaitAdvance` và timeout methods được dùng đúng.
- [ ] Lỗi worker, timeout và cancellation có policy forceTerminate/cleanup rõ.
- [ ] Callback `onAdvance` nằm ở root, không blocking và không thao tác lại cùng Phaser.
- [ ] Root termination policy hợp với việc các groups có thể rỗng rồi hoạt động lại.
- [ ] Không dùng `getRegisteredParties` của root như tổng workforce toàn cây.
- [ ] Memory visibility/partition ownership được đảm bảo, tránh races.
- [ ] Đã test empty child, lazy registration, group deregister, multi-phase, three-level, timeout.
- [ ] Chỉ thêm tiering khi benchmark cho thấy lợi ích vượt overhead.

## 25. Tự kiểm tra

**1. Child có 500 parties chiếm bao nhiêu ở parent?** Một party, khi child còn ít nhất một party đã đăng ký.

**2. Child tạo bằng `new Phaser(parent,0)` có chiếm parent party?** Không.

**3. Child `bulkRegister(3)` từ 0 làm parent tăng bao nhiêu?** Một.

**4. Child còn 2, một party `arriveAndDeregister`, parent giảm chưa?** Chưa, child vẫn nonempty.

**5. Child từ 1 xuống 0 nhờ `arriveAndDeregister`, parent có tự giảm?** Có.

**6. Root.getRegisteredParties có là tổng toàn cây?** Không, chỉ tại root.

**7. `getRoot()` của grandchild trả gì?** Root ancestor của toàn cây.

**8. `arriveAndAwaitAdvance()` có timeout tham số?** Không; tách arrive và awaitAdvanceInterruptibly để dùng timeout.

**9. Timeout có tự rút party?** Không.

**10. Trong cây, callback `onAdvance` chạy ở đâu?** Root.

**11. Root terminated có sống lại chỉ với `register()`?** Không.

**12. `forceTermination()` có xóa counts hoặc shutdown executor?** Không.

**13. Một cây tổng 16.000 parties có buộc cần 16.000 threads?** Không.

**14. Giới hạn 65.535 của implementation áp dụng thế nào?** Trên từng Phaser node, không phải tổng của cây.

**15. Tiering luôn nhanh hơn flat?** Không, giảm contention nhưng tăng per-operation overhead.

**16. Vì sao phase root có thể chờ mãi dù children hoàn tất?** Root còn coordinator/party chưa arrive, hoặc đăng ký dư phantom party.

**17. Vì sao pool cố định ít threads gây starvation?** Các threads đã có thể cùng chờ các tasks chưa được chạy; không đủ execution capacity.

**18. Vì sao không dùng snapshots getArrivedParties để điều khiển phase?** Snapshot có thể đổi ngay; dùng barrier methods.

**19. Root callback luôn cần trả false?** Không; trả true khi cần terminate theo lifecycle chính xác.

**20. Ba ý quan trọng nhất?** **Child nonempty chiếm một party ở parent; toàn cây advance ở root; đo contention trước khi quyết định phân tầng.**

## 26. Nguồn tài liệu chính thức

- [Oracle Java SE 25 — Phaser](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Phaser.html): tiering, registration, arrival/await, timeout, termination, callback, per-node limit và memory consistency.
- [Oracle Java SE 17 — Phaser](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Phaser.html): bản API tương ứng JDK 17 dùng kiểm thử.
- [Oracle Java SE 7 — Phaser](https://docs.oracle.com/javase/7/docs/api/java/util/concurrent/Phaser.html): xác nhận API gốc từ Java 7, không dùng làm chuẩn thay cho bản hiện hành.
- [Oracle Java SE 25 — CyclicBarrier](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CyclicBarrier.html): barrier có số parties cố định.
- [Oracle Java SE 25 — CountDownLatch](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CountDownLatch.html): cơ chế một lần, khác reusable Phaser.
- [Oracle Java SE 25 — ForkJoinPool](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): khi kết hợp với waiting parties và worker capacity.
- [Oracle Java SE 25 — ExecutorService](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html): shutdown và lifecycle workers.
- [Oracle Java SE 25 — Future](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html): chờ workers, timeout và lỗi.
- [Oracle Java SE 25 — AtomicIntegerArray](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicIntegerArray.html): đếm hoàn tất nhiều threads.
- [OpenJDK JMH](https://github.com/openjdk/jmh): microbenchmark Java/JVM.

**Kết luận:** `Phaser` phân tầng là một cách tổ chức barrier **vẫn được hỗ trợ trong Java hiện đại**, có ích khi quá nhiều parties tranh chấp trên một Phaser phẳng. Mỗi child nonempty chỉ đại diện **một party** tại parent và tự deregister khi rỗng. Toàn cây có phase chung, callback ở root và termination ảnh hưởng mọi tầng. Hãy thiết kế ownership/arrival/timeout đúng, phân biệt logic parties với threads, rồi **đo** flat và tiered trên workload thực để chọn số nhóm và độ sâu phù hợp.
