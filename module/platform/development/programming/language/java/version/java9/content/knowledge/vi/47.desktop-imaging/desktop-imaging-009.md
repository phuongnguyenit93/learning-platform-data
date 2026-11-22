# Java 9+: `@BeanProperty`, `@JavaBean` và `@SwingContainer` cho metadata giao diện

## 1. Vì sao giao diện desktop cần metadata JavaBeans?

Một thư viện thành phần giao diện có thể được dùng trong *GUI builder*, property inspector hoặc công cụ cấu hình. Những công cụ này cần biết: lớp/component mô tả gì, thuộc tính nào nên hiển thị trước, thuộc tính nào dành cho chuyên gia, giá trị nào là bắt buộc và nếu component nhận con thì các component con nên thêm vào đâu.

**JavaBeans Introspection** là cơ chế tiêu chuẩn của Java cho phép công cụ đọc thông tin của một lớp thông qua tên phương thức như `getTitle()`, `setTitle(...)`, `isEnabled()`, các sự kiện kiểu `add...Listener`/`remove...Listener` và đối tượng metadata `BeanInfo`. Từ **Java 9 (JEP 256)**, Java cung cấp ba annotation giúp gắn metadata trực tiếp trên mã nguồn lớp/phương thức để `Introspector` tạo `BeanInfo` tự động:

- `@JavaBean` — mô tả **toàn bộ bean**: chú thích lớp và thuộc tính/sự kiện mặc định.
- `@BeanProperty` — mô tả **một thuộc tính** JavaBeans qua getter hoặc setter: mức ưu tiên, thuộc tính bound, mô tả, giá trị gợi ý...
- `@SwingContainer` — mô tả **component Swing như một container trong công cụ thiết kế**, gồm khả năng nhận các component con và phương thức trả về container nhận con.

**Phạm vi hiện hành:** cả ba annotation vẫn hiện diện trong module **`java.desktop`** của Java SE hiện nay, dùng được trên JDK 17+ và các JDK mới hơn. Đây là metadata cho JavaBeans/Swing và công cụ đọc `BeanInfo`; **không biến annotation thành cơ chế tự sinh UI, tự validate hoặc tự repaint**. Dùng chúng khi dự án thực sự có GUI builder, property editor, component library hoặc introspection runtime.

## 2. Ba annotation cùng làm gì và khác nhau thế nào?

| Annotation | Package | Gắn ở đâu? | Metadata tiêu biểu |
|---|---|---|---|
| `@JavaBean` | `java.beans` | **Class/interface type** — `@Target(TYPE)` | `description`, `defaultProperty`, `defaultEventSet` |
| `@BeanProperty` | `java.beans` | **Method** — `@Target(METHOD)`, thường getter | `description`, `bound`, `expert`, `hidden`, `preferred`, `required`, `visualUpdate`, `enumerationValues` |
| `@SwingContainer` | `javax.swing` | **Class/type** — `@Target(TYPE)` | `value` (có nên coi là container?), `delegate` (tên getter của container nhận con) |

Cả ba đều có **`@Retention(RUNTIME)`**, cho phép sử dụng trong lúc chạy thông qua JavaBeans introspection. `@JavaBean` và `@BeanProperty` còn có `@Documented`. Không cần thư viện ngoài: API thuộc JDK (module `java.desktop`).

Các annotation được dùng khi `Introspector` **tự phân tích** bean. Theo Javadoc, nếu lớp có một **`BeanInfo` tự định nghĩa** khiến phân tích tự động bị bỏ qua, các annotation này không được dùng trong nhánh tương ứng. Vì vậy hãy kiểm tra kết quả `Introspector.getBeanInfo(...)` thực tế nếu một thư viện đã cung cấp `SomeComponentBeanInfo` riêng.

## 3. `@JavaBean` — metadata ở cấp lớp

Khai báo:

~~~java
import java.beans.JavaBean;

@JavaBean(
    description = "Thanh thông báo có nhãn và vùng chứa nội dung",
    defaultProperty = "caption"
)
public class NoticePanel {
    // Chỉ là khai báo minh họa; ví dụ đầy đủ ở phần 7.
}
~~~

Ba thành phần của `@JavaBean`:

| Thành phần | Mặc định | Ý nghĩa |
|---|---|---|
| `description` | `""` | Mô tả ngắn của bean, xuất hiện trong `BeanDescriptor.getShortDescription()`. |
| `defaultProperty` | `""` | **Tên thuộc tính** được GUI builder ưu tiên khi chỉnh sửa. `Introspector` chuyển tên này thành `BeanInfo.getDefaultPropertyIndex()` trong mảng `PropertyDescriptor[]`. |
| `defaultEventSet` | `""` | **Tên bộ sự kiện** mặc định, được chuyển thành `BeanInfo.getDefaultEventIndex()` trong mảng `EventSetDescriptor[]`. |

Ví dụ bean có phương thức `getCaption()` và `setCaption(String)` thì tên property là **`caption`**, không phải `getCaption`. Do đó `defaultProperty = "caption"` mới khớp.

Đối với `defaultEventSet`, tên phải khớp một event set **thực sự được `Introspector` nhận diện**. Nếu không có thuộc tính/sự kiện tên đã khai báo, Javadoc cho phép `Introspector` tính chỉ số mặc định theo trạng thái hiện tại; trong công cụ tiêu thụ metadata, luôn **kiểm tra chỉ số có hợp lệ** trước khi dùng (thường `-1` nghĩa là không có mặc định). Không giả định annotation tự tạo ra thuộc tính hay sự kiện.

**`@JavaBean` không bắt buộc có trên mọi JavaBean.** Một lớp có `getX`/`setX` đúng quy ước vẫn có thể được `Introspector` phát hiện mà không cần annotation. Annotation bổ sung metadata phục vụ hiển thị/thiết kế.

## 4. `@BeanProperty` — metadata của từng thuộc tính

JavaBeans xem các phương thức getter/setter theo quy ước là một *property*. Annotation `@BeanProperty` đặt trên **phương thức** cho phép bổ sung thông tin khi `Introspector` sinh `PropertyDescriptor`:

~~~java
import java.beans.BeanProperty;

@BeanProperty(
    description = "Nội dung được hiển thị ở phần đầu",
    preferred = true,
    bound = true,
    required = true,
    visualUpdate = true
)
public String getCaption() {
    return caption;
}
~~~

Có thể gắn annotation lên setter. **Khi cả getter và setter của cùng property đều có `@BeanProperty`, annotation trên getter được ưu tiên và thay thế annotation trên setter** theo Javadoc. Vì vậy, thông thường nên đặt tại getter để tránh metadata mâu thuẫn.

### 4.1. Các phần tử của `@BeanProperty`

| Phần tử | Mặc định | Tác động lên metadata |
|---|---|---|
| `description` | `""` | Mô tả ngắn của `PropertyDescriptor`; đọc qua `getShortDescription()`. |
| `bound` | `true` | Đánh dấu property là **bound** nếu bean có event set `propertyChange`; đọc qua `PropertyDescriptor.isBound()`. |
| `expert` | `false` | Dành cho chế độ nâng cao của property editor; đọc qua `isExpert()`. |
| `hidden` | `false` | Đánh dấu không nên hiển thị cho người dùng thông thường; đọc qua `isHidden()`. |
| `preferred` | `false` | Đánh dấu property quan trọng nên được ưu tiên hiển thị; đọc qua `isPreferred()`. |
| `required` | `false` | Gợi ý property bắt buộc; lưu dưới feature attribute `"required"`; đọc qua `getValue("required")`. |
| `visualUpdate` | `false` | Metadata cho công cụ biết việc đổi property liên quan cập nhật hiển thị; đọc qua `getValue("visualUpdate")`. |
| `enumerationValues` | mảng rỗng | Danh sách tên field `public static` để công cụ xây các giá trị có thể lựa chọn. |

**Hai giới hạn đặc biệt quan trọng:**

1. **`bound = true` không tự phát ra `PropertyChangeEvent`.** Bean phải có cơ chế listener và setter phải **thực sự phát sự kiện** khi giá trị đổi. Với Swing, `JComponent`/`Component` có sẵn `addPropertyChangeListener` và `firePropertyChange`; với POJO dùng `PropertyChangeSupport`.
2. **`required = true` không tự kiểm tra `null` hay chặn setter; `visualUpdate = true` không tự gọi `repaint()`.** Đây là metadata mà công cụ có thể lựa chọn tuân theo. Nếu muốn validate dữ liệu hoặc cập nhật giao diện, hãy viết logic trong setter/ứng dụng.

### 4.2. `enumerationValues` dành cho property editor

Với giá trị thuộc một tập hữu hạn, có thể chỉ định tên các field `public static` để BeanInfo tạo feature attribute `"enumerationValues"`:

~~~java
// Mã minh họa trong một bean, không phải chương trình main độc lập.
public static final int VIEW_LIST = 1;
public static final int VIEW_GRID = 2;

private int viewMode = VIEW_LIST;

@BeanProperty(
    description = "Cách hiển thị nội dung",
    enumerationValues = {"VIEW_LIST", "VIEW_GRID"}
)
public int getViewMode() {
    return viewMode;
}

public void setViewMode(int viewMode) {
    this.viewMode = viewMode;
}
~~~

`PropertyDescriptor.getValue("enumerationValues")` sẽ chứa dữ liệu phục vụ bộ chọn/nguồn sinh code; trong JDK, các mục được biểu diễn theo nhóm **tên hiển thị, giá trị thực, biểu thức mã Java** của từng lựa chọn. Ví dụ được kiểm chứng với `VIEW_LIST=1` và `VIEW_GRID=2` cho mảng kiểu:

~~~text
[VIEW_LIST, 1, VIEW_LIST, VIEW_GRID, 2, VIEW_GRID]
~~~

Đây là **metadata dành cho công cụ** chứ không thay thế kiểm tra đầu vào trong `setViewMode`. Nếu muốn giới hạn giá trị hợp lệ trong runtime, setter phải tự kiểm tra hoặc dùng kiểu dữ liệu phù hợp.

## 5. `@SwingContainer` — metadata dành cho GUI builder Swing

Một điều dễ nhầm: rất nhiều thành phần Swing kế thừa `java.awt.Container`, nhưng **không phải thành phần nào cũng nên được GUI builder cho phép thả thêm component con vào trực tiếp**. Với một số component, vị trí chứa con thực tế còn là một container lồng bên trong.

`@SwingContainer` cung cấp hai thành phần:

| Thành phần | Mặc định | Ý nghĩa |
|---|---|---|
| `value` | `true` | `true` nếu lớp nên được xem là một container nhận Swing component con trong GUI builder; `false` nếu không nên được sử dụng như container trong công cụ thiết kế. |
| `delegate` | `""` | **Tên phương thức getter** của bean trả về container nhận con thực tế, ví dụ `"getContentPane"`. Để rỗng nếu không có delegate. |

Ví dụ:

~~~java
import javax.swing.SwingContainer;

@SwingContainer(value = true, delegate = "getContentPane")
public class CustomPanel {
    // Khai báo minh họa; ví dụ chạy đầy đủ bên dưới.
}
~~~

Thông tin được đưa vào `BeanDescriptor` dưới các feature attributes:

~~~java
BeanInfo info = Introspector.getBeanInfo(CustomPanel.class);
Object isContainer = info.getBeanDescriptor().getValue("isContainer");
Object delegateName = info.getBeanDescriptor().getValue("containerDelegate");
~~~

Với annotation trên, giá trị tương ứng là `true` và `"getContentPane"`. `delegate` phải là tên getter có thật, được dùng bởi công cụ tích hợp, trả về `java.awt.Container` thích hợp.

**Quan trọng:** `@SwingContainer` **không tự chuyển hướng** lời gọi `add(child)` tại runtime, không tự thêm container con vào cây Swing và không tự áp dụng layout. GUI builder đọc metadata rồi quyết định nơi đặt child. Lớp Swing vẫn cần constructor, cấu trúc component và layout đúng.

Ví dụ `@SwingContainer(false)` hợp lý nếu bạn tạo một component chỉ để hiển thị mà không muốn GUI builder đề nghị thêm component con. Đây cũng chỉ là quy tắc hiển thị của builder, không cấm Java code gọi một phương thức `add(...)` còn khả dụng từ lớp cha.

## 6. `Introspector` chuyển annotation thành những descriptor nào?

`java.beans.Introspector.getBeanInfo(SomeBean.class)` phân tích bean và tạo `BeanInfo`; ứng dụng/tool có thể đọc:

| API | Dữ liệu |
|---|---|
| `beanInfo.getBeanDescriptor()` | Metadata toàn bean: mô tả, các feature attributes như `isContainer` / `containerDelegate`. |
| `beanInfo.getPropertyDescriptors()` | Các property theo quy ước getter/setter: kiểu dữ liệu, read/write method, `bound`, `preferred`, `hidden`, `required`... |
| `beanInfo.getEventSetDescriptors()` | Các event set nhận diện từ quy ước listener của JavaBeans. |
| `beanInfo.getDefaultPropertyIndex()` | Chỉ số property mặc định trong mảng property descriptors; có thể không có. |
| `beanInfo.getDefaultEventIndex()` | Chỉ số event set mặc định trong mảng event descriptors; có thể không có. |

Có hai kiểu dữ liệu bạn thường gặp:

- **Thuộc tính trực tiếp** của `FeatureDescriptor`: `getName()`, `getShortDescription()`, `isExpert()`, `isHidden()`, `isPreferred()`.
- **Feature attribute tùy chọn**: `descriptor.getValue("required")`, `getValue("visualUpdate")`, hoặc ở mức bean `getValue("isContainer")`, `getValue("containerDelegate")`. Các attribute này có thể trả `null` nếu không được đặt, vì thế đừng ép kiểu tùy tiện.

Sơ đồ xử lý:

~~~text
class + public getters/setters + JavaBeans listener methods
             |
   @JavaBean / @BeanProperty / @SwingContainer
             |
      Introspector.getBeanInfo(Class)
             |
       +-----+------------------+
       |                        |
   BeanDescriptor       PropertyDescriptor[]
   - description        - name/type/getter/setter
   - isContainer        - description/bound/preferred
   - containerDelegate  - required/visualUpdate/...
             |
        GUI builder / property editor
             |
        Hiển thị metadata hoặc gợi ý thao tác thiết kế
~~~

Không nên coi annotation là *reflection API* thay thế introspection: mặc dù `@Retention(RUNTIME)` giúp `Class.getAnnotation(...)` hoặc `Method.getAnnotation(...)` đọc trực tiếp, **đầu ra chuẩn dành cho JavaBeans tool là `BeanInfo` và các descriptor**.

`Introspector` có cơ chế cache. Trong tình huống đặc biệt ứng dụng thay đổi thông tin `BeanInfo`/classloader khi đang chạy, có thể dùng `Introspector.flushFromCaches(SomeBean.class)` hoặc `flushCaches()` theo nhu cầu quản lý cache; thông thường không cần gọi các phương thức này cho những lớp được định nghĩa cố định.

## 7. Ví dụ Java 17+ độc lập: cả ba annotation trong một Swing component

Ví dụ sử dụng `JPanel`, hoạt động ngay cả khi chạy không có cửa sổ GUI. Nó chứng minh `Introspector` thực sự đọc annotation và nhận ra `PropertyChangeEvent` từ setter.

Tạo file **`BeanMetadataDemo.java`**:

~~~java
import java.awt.BorderLayout;
import java.awt.Container;
import java.beans.BeanDescriptor;
import java.beans.BeanInfo;
import java.beans.BeanProperty;
import java.beans.Introspector;
import java.beans.JavaBean;
import java.beans.PropertyDescriptor;
import java.util.Arrays;
import javax.swing.JPanel;
import javax.swing.SwingContainer;

public class BeanMetadataDemo {
    @JavaBean(
            description = "Bang thong bao",
            defaultProperty = "caption")
    @SwingContainer(value = true, delegate = "getContentPane")
    public static class NoticePanel extends JPanel {
        private String caption = "Ready";
        private final JPanel contentPane = new JPanel();

        public NoticePanel() {
            super(new BorderLayout());
            add(contentPane, BorderLayout.CENTER);
        }

        // GUI builder có thể chọn container thật này để thêm con.
        public Container getContentPane() {
            return contentPane;
        }

        @BeanProperty(
                description = "Noi dung thong bao",
                bound = true,
                preferred = true,
                required = true,
                visualUpdate = true)
        public String getCaption() {
            return caption;
        }

        public void setCaption(String value) {
            String old = caption;
            caption = value;
            // Đây mới là hành vi thực sự phát PropertyChangeEvent.
            firePropertyChange("caption", old, value);
            repaint(); // Cập nhật UI do code thực hiện, không do annotation.
        }
    }

    public static void main(String[] args) throws Exception {
        BeanInfo info = Introspector.getBeanInfo(NoticePanel.class);
        BeanDescriptor bean = info.getBeanDescriptor();

        PropertyDescriptor caption = Arrays.stream(
                info.getPropertyDescriptors())
                .filter(p -> p.getName().equals("caption"))
                .findFirst()
                .orElseThrow();

        System.out.println("Bean: " + bean.getShortDescription());
        int index = info.getDefaultPropertyIndex();
        System.out.println("Default property: "
                + info.getPropertyDescriptors()[index].getName());
        System.out.println("Swing container: "
                + bean.getValue("isContainer"));
        System.out.println("Delegate: "
                + bean.getValue("containerDelegate"));
        System.out.println("Property: "
                + caption.getShortDescription());
        System.out.println("Bound: " + caption.isBound());
        System.out.println("Preferred: " + caption.isPreferred());
        System.out.println("Required: "
                + caption.getValue("required"));
        System.out.println("Visual update: "
                + caption.getValue("visualUpdate"));

        NoticePanel panel = new NoticePanel();
        panel.addPropertyChangeListener("caption",
                e -> System.out.println(
                        "Changed: " + e.getNewValue()));
        panel.setCaption("Updated");
    }
}
~~~

Chạy bằng Java 17+ (module `java.desktop` là thành phần tiêu chuẩn của JDK):

~~~bash
javac BeanMetadataDemo.java
java BeanMetadataDemo
~~~

Stdout đã được đối chiếu với **OpenJDK 24**:

~~~text
Bean: Bang thong bao
Default property: caption
Swing container: true
Delegate: getContentPane
Property: Noi dung thong bao
Bound: true
Preferred: true
Required: true
Visual update: true
Changed: Updated
~~~

**Giải thích theo dòng kết quả:**

1. `Bean: ...` và `Default property: caption` do `@JavaBean` tạo metadata ở mức class.
2. `Swing container: true` và `Delegate: getContentPane` đến từ `@SwingContainer`, lưu ở `BeanDescriptor`.
3. `Property: ...`, `Bound`, `Preferred`, `Required`, `Visual update` lấy từ annotation `@BeanProperty` trên getter `getCaption()`.
4. `Changed: Updated` **không được annotation tự sinh**: đây là callback nhận `PropertyChangeEvent` do setter gọi `firePropertyChange`.
5. Constructor thực sự thêm `contentPane` vào `JPanel` để có cấu trúc UI hợp lệ. Annotation delegate chỉ để công cụ thiết kế biết container nào nên nhận component con.

Class ví dụ dùng chuỗi ASCII trong `description` và output để có stdout dễ đối chiếu trên nhiều terminal. Trong ứng dụng thực tế có thể mô tả bằng tiếng Việt và hiển thị trong GUI builder có hỗ trợ mã hóa Unicode.

Nếu viết ứng dụng dạng Java module có `module-info.java`, khai báo:

~~~java
module demo.beans.gui {
    requires java.desktop;
}
~~~

Không cần dependency Maven/Gradle riêng cho các annotation này.

## 8. Ứng dụng trong giao diện Swing thực tế

### 8.1. Property inspector

Một công cụ thiết kế có thể lấy danh sách property:

~~~java
// Đoạn minh họa, không phải chương trình độc lập:
BeanInfo info = Introspector.getBeanInfo(NoticePanel.class);
for (PropertyDescriptor descriptor : info.getPropertyDescriptors()) {
    if (descriptor.isHidden()) {
        continue;
    }
    System.out.println(descriptor.getName()
            + " | " + descriptor.getShortDescription()
            + " | preferred=" + descriptor.isPreferred());
}
~~~

`isHidden()` chỉ là **gợi ý** cho công cụ. Không nên dùng nó để ngăn truy cập tài liệu nhạy cảm hoặc che một API công khai; Java code vẫn có thể gọi getter/setter theo quyền truy cập bình thường.

### 8.2. GUI builder có vùng chứa riêng

Giả sử bạn tạo component dạng “card” có header và body panel. GUI builder có thể đọc `delegate = "getContentPane"` rồi chỉ thêm child vào body panel theo quy ước thiết kế. Điều này hữu ích hơn việc mặc định thả child trực tiếp vào lớp cha.

Một builder không hiểu `@SwingContainer` sẽ không tự thực hiện hành vi delegate. Khi đó, API thiết kế component hoặc hướng dẫn sử dụng cần cung cấp cách thêm con đúng, ví dụ `panel.getContentPane().add(child)`.

### 8.3. Khi nào nên dùng annotation, khi nào không cần?

| Nhu cầu | Gợi ý |
|---|---|
| Thiết kế component Swing sẽ được khám phá bằng `Introspector` | Dùng `@JavaBean`/`@BeanProperty` để thể hiện metadata có ích; `@SwingContainer` nếu builder cần biết vùng chứa. |
| Thư viện component có nhiều getter/setter và property inspector riêng | Có thể dùng annotation cùng `BeanInfo` để gợi ý thứ tự, mô tả và nhóm giá trị; phải kiểm tra `BeanInfo` được tool thực sự tiêu thụ. |
| Chỉ viết một Swing form bằng code tay | Không bắt buộc thêm annotation; dùng getter/setter, layout, event listener bình thường. |
| Cần validation nghiệp vụ tại runtime | Viết logic setter/service hoặc cơ chế validation thích hợp; `required` không tự validate. |
| Cần tự động redraw khi dữ liệu đổi | Gọi `repaint()`/`revalidate()` phù hợp trên EDT và sử dụng mô hình Swing đúng; `visualUpdate` không thực thi redraw. |
| Cần quản lý thread UI | Sử dụng **Swing Event Dispatch Thread (EDT)** để cập nhật UI; annotation JavaBeans không thay thế quy tắc này. |

## 9. Lỗi thường gặp và cách sửa

**Lỗi 1: Dùng sai tên property.** Annotation `@JavaBean(defaultProperty = "getCaption")` thay vì `"caption"` khiến default property không khớp. `Introspector` suy ra tên từ cặp `getCaption()`/`setCaption(...)` theo quy ước JavaBeans.

**Lỗi 2: Đặt `@BeanProperty` lên field.** Annotation có `@Target(METHOD)`, nên phải gắn lên getter hoặc setter. Với cả hai được chú thích, getter có ưu tiên.

**Lỗi 3: Cho rằng `bound=true` sẽ phát event.** Nếu setter không phát `PropertyChangeEvent` (hoặc bean không có `propertyChange` event set), listener sẽ không nhận thông báo. Trong Swing có thể dùng `firePropertyChange(...)`, với POJO dùng `PropertyChangeSupport` và các phương thức đăng ký listener.

**Lỗi 4: `required=true` được hiểu là `@NotNull`.** Đây là feature attribute `"required"` phục vụ UI builder/property editor, không phải một constraint được Java runtime tự động kiểm tra. Việc chặn giá trị không hợp lệ phải tự thực hiện.

**Lỗi 5: `visualUpdate=true` được hiểu là gọi `repaint()`.** Metadata không thực thi hành vi UI. Cập nhật component trên EDT, gọi `repaint()`/`revalidate()` khi cần; ví dụ phần 7 thể hiện rõ hai bước riêng.

**Lỗi 6: `@SwingContainer(value=true)` tự chuyển mọi `add(child)` vào `delegate`.** Sai. Metadata chỉ giúp tool quyết định container, còn phương thức `add(...)` của đối tượng vẫn hoạt động theo code Java/Swing hiện hữu.

**Lỗi 7: `delegate` là tên field thay vì tên getter.** Javadoc yêu cầu tên của **getter method** trả về container. Với ví dụ, đặt `"getContentPane"`, không đặt `"contentPane"`.

**Lỗi 8: Có custom `BeanInfo` nhưng mong annotation tự ghi đè.** Nếu BeanInfo tự định nghĩa khiến introspection tự động không chạy, annotation không được dùng trong nhánh đó. Hãy kiểm tra kết quả thực `Introspector.getBeanInfo(...)` và chọn chiến lược metadata nhất quán.

**Lỗi 9: Giả định mọi getter sẽ xuất hiện mà không cần quy ước.** JavaBeans nhận diện `getX()` (getter thường), `isX()` (boolean), `setX(...)` (setter), cùng các quy tắc tên property. Getter tự đặt tên khác có thể không được công cụ đọc như property chuẩn.

**Lỗi 10: Nhầm metadata với bảo mật hoặc API bắt buộc.** `hidden`/`expert`/`preferred` không chặn gọi phương thức, `required` không đảm bảo dữ liệu hợp lệ, và `@SwingContainer` không cưỡng chế cấu trúc cây Swing. Các quy tắc nghiệp vụ và bảo mật vẫn phải cài đặt trong mã chạy.

## 10. Câu hỏi tự kiểm tra

1. **`@JavaBean` khác `@BeanProperty` ở đâu?** — `@JavaBean` mô tả class/bean; `@BeanProperty` mô tả một property được nhận diện qua method getter/setter.
2. **`@SwingContainer(delegate="getContentPane")` khiến `panel.add(child)` tự chuyển vào `getContentPane()` không?** — Không. GUI builder có thể sử dụng metadata để quyết định cách thêm con; runtime không tự sửa hành vi `add`.
3. **`@BeanProperty(bound=true)` đã đủ để listener nhận thông báo chưa?** — Chưa. Bean phải hỗ trợ propertyChange event set và setter phải thực sự phát event.
4. **`required=true` có tự từ chối chuỗi rỗng không?** — Không. Đây là metadata; cần validation trong code.
5. **Làm sao đọc default property?** — Gọi `BeanInfo.getDefaultPropertyIndex()`, kiểm tra chỉ số hợp lệ rồi truy cập `getPropertyDescriptors()[index]`.
6. **Làm sao đọc tên container delegate?** — Gọi `Introspector.getBeanInfo(MyClass.class).getBeanDescriptor().getValue("containerDelegate")`.
7. **Nếu getter và setter cùng có `@BeanProperty` khác nhau?** — Annotation của getter có ưu tiên theo Javadoc.
8. **Ba annotation này có còn dùng trên JDK hiện nay?** — Có, thuộc module `java.desktop`; chúng hữu ích khi JavaBeans/Swing metadata còn được công cụ tiêu thụ.

## Tài liệu tham khảo hiện hành

- [Java SE 26 — `java.beans.JavaBean`](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/java/beans/JavaBean.html): `description`, `defaultProperty`, `defaultEventSet` và phạm vi áp dụng.
- [Java SE 26 — `java.beans.BeanProperty`](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/java/beans/BeanProperty.html): các thuộc tính property và quy tắc ưu tiên getter.
- [Java SE 26 — `javax.swing.SwingContainer`](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/javax/swing/SwingContainer.html): `value`, `delegate`, metadata `isContainer` của Swing GUI builder.
- [Java SE 26 — `java.beans.Introspector`](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/java/beans/Introspector.html): tạo `BeanInfo` và cơ chế cache.
- [Java SE 26 — `java.beans.BeanInfo`](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/java/beans/BeanInfo.html): bean/property/event descriptors và default indices.
- [Java SE 26 — `java.beans.PropertyDescriptor`](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/java/beans/PropertyDescriptor.html): property methods, `isBound` và metadata.
- [Java SE 26 — `java.beans.FeatureDescriptor`](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/java/beans/FeatureDescriptor.html): `getShortDescription`, `isPreferred`, `getValue`.
- [OpenJDK JEP 256 — BeanInfo Annotations](https://openjdk.org/jeps/256): thay đổi được giới thiệu từ Java 9.

**Ghi nhớ:** `@JavaBean` mô tả **bean**, `@BeanProperty` mô tả **thuộc tính**, còn `@SwingContainer` cung cấp **hướng dẫn container cho công cụ Swing**. Chúng bổ sung metadata vào `BeanInfo`; tác động runtime như phát event, kiểm tra dữ liệu và vẽ lại giao diện vẫn phải được triển khai bằng Java code.
