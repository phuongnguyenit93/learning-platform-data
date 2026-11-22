# Do not narrow access scope when overriding methods in Java

An override must preserve or **widen** the access privileges of the overridden method. If a parent class exposes a public method, a subclass cannot make that method protected or package-private: calling code that is valid through the parent type must continue to work when the actual object is an instance of the subclass.

## 1. Visibility rules

| Parent method | Valid visibility in override | Invalid |
| --- | --- | --- |
| public | public | protected, package-private, private |
| protected | protected, public | package-private, private |
| Package-private | Preserve or widen when it can actually be overridden | private; or the case in a different package where that method is not inherited |
| private | No override for that private method | Visibility scale does not apply |

In a class, omitting a modifier means package-private. A parent's private method is not inherited for overriding; a method with the same name in the child is a separate declaration. For package-private, the package must be considered: a subclass in a different package cannot see that method to override it. If a package-private method is abstract, a concrete subclass in a different package cannot fulfill the contract merely by declaring a method with the same name.

## 2. Example: widening access privileges

~~~java
package academy.reports;

public abstract class Report {
    public abstract String title();
    protected abstract int pages();
    abstract String marker();
}
~~~

~~~java
package academy.reports;

public final class MonthlyReport extends Report {
    @Override
    public String title() {
        return "Monthly";
    }

    @Override
    public int pages() {          // protected -> public
        return 12;
    }

    @Override
    protected String marker() {   // package-private -> protected
        return "2026-10";
    }
}
~~~

The two classes are in the same package, so MonthlyReport.marker() actually overrides the parent's package-private method. pages() is widened to public so callers outside the package can call it through the MonthlyReport type.

Even though MonthlyReport.pages() is public, the call report.pages() through a variable with static type Report in another package is still invalid, because the declaration visible through Report is protected. Access privileges are checked at compile time according to the static type and protected rules; the runtime object does not automatically elevate privileges for the call.

## 3. Interfaces always require public for instance methods

~~~java
interface Sender {
    void send(); // implicitly public abstract
}

final class EmailSender implements Sender {
    @Override
    public void send() {
        System.out.println("sent");
    }
}
~~~

The implementing class must not omit public from send(): in a class, a method without a modifier is package-private, which is weaker than the interface's public contract. The same rule applies when overriding a public default method.

## 4. Diagnosing errors

~~~java
class Document {
    public String name() { return "Document"; }
}

class PdfDocument extends Document {
    @Override
    protected String name() { return "PDF"; } // Invalid
}
~~~

The compiler typically reports an error about *weaker access privileges*. Removing @Override does not fix the error; the declaration is still overriding with weaker access privileges.

**Checklist:** compare the visibility on the parent/interface method with the child method; check the package if the parent uses package-private; and do not confuse access privileges with runtime dispatch. This lesson focuses on visibility; compatibility of return types and checked exceptions is explained in separate lessons.
