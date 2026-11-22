# `public`, `protected`, and Package-Private Scope of Abstract Methods in Java

An access modifier determines which code can call a method and which subclasses can override it. For an `abstract` method in a class, Java allows `public`, `protected`, or package-private (no modifier specified). These three choices create contracts with different scopes.

## 1. Comparing the three access levels

```java
public abstract class Task {
    public abstract String title();
    protected abstract int priority();
    abstract String internalCode();
}
```

| Declaration in class | Callable by code in the same package? | Can a subclass in another package override it? | Can regular code in another package call it directly? |
|---|---|---|---|
| `public abstract` | Yes | Yes; the override must be `public` | Yes, if the enclosing type is accessible |
| `protected abstract` | Yes | Yes; the override must be `protected` or `public` | Not arbitrarily; it must satisfy `protected` rules |
| package-private `abstract` | Yes | No, not by declaring the same signature in another package | No |

Package-private is sometimes called *default access*. This is not the `default` keyword used to declare a method with a body in an interface. Package-private access is based on the Java package declared in the source, not on whether two packages have similar names or reside in the same parent directory.

## 2. Visibility rules when overriding

A subclass may keep or widen the access level of a method it actually overrides; it must not narrow it:

| Modifier in superclass | Valid override modifiers |
|---|---|
| `public` | `public` |
| `protected` | `protected`, `public` |
| package-private | package-private, `protected`, `public` if the subclass is actually in the same package and sees the method |

Incorrect example:

```java
abstract class Job {
    public abstract void run();
}

class BadJob extends Job {
    @Override
    protected void run() { // Error: weakens public to protected
        System.out.println("run");
    }
}
```

Fix it to `public void run()`. Use `@Override` so the compiler checks that the signature actually overrides an inherited method. Changing visibility cannot turn a method that is not visible into a valid override.

## 3. Runnable example: calling the public API, keeping internal hooks

The files below are in the same package `academy.tasks`, except for `Main` in package `app`.

**`src/academy/tasks/Task.java`**

```java
package academy.tasks;

public abstract class Task {
    public abstract String title();
    protected abstract int points();
    abstract String code();

    public final String summary() {
        return title() + " | " + points() + " | " + code();
    }
}
```

**`src/academy/tasks/ReviewTask.java`**

```java
package academy.tasks;

public final class ReviewTask extends Task {
    @Override
    public String title() {
        return "Review";
    }

    @Override
    protected int points() {
        return 3;
    }

    @Override
    String code() {
        return "REV-01";
    }
}
```

**`src/app/Main.java`**

```java
package app;

import academy.tasks.ReviewTask;
import academy.tasks.Task;

public class Main {
    public static void main(String[] args) {
        Task task = new ReviewTask();
        System.out.println(task.title());
        System.out.println(task.summary());
    }
}
```

Compile from the directory containing `src`:

```bash
javac -encoding UTF-8 -d out src/academy/tasks/Task.java src/academy/tasks/ReviewTask.java src/app/Main.java
java -cp out app.Main
```

Output:

```text
Review
Review | 3 | REV-01
```

`Main` can call `title()` and `summary()` because they are public. `points()` is protected, and `code()` is package-private; code in `app` cannot call these two methods directly. However, `summary()` can call them inside `Task`, where access is valid, and dynamic dispatch selects the implementation in `ReviewTask`. Access restrictions in source code do not prevent valid internal calls to the implementation.

## 4. When a subclass is in another package

A subclass in another package can override `protected abstract` or `public abstract` if it complies with the signature and visibility. For a package-private abstract method, declaring a method with the same name and parameters in another package does **not** fulfill the superclass contract; a direct concrete subclass still has an unimplemented abstract method.

If a class outside the package must provide its own implementation, design the hook as `protected abstract` or `public abstract`. If the hook must be kept internal to the superclass's package, you can have a class in the same package implement it before extending the hierarchy outside. The dedicated article on package-private across packages covers this case and how to implement an intermediate class in more detail.

## 5. Interface differences

A regular abstract method in an interface is `public abstract` by default, not package-private:

```java
public interface Action {
    void execute(); // implicitly public abstract
}

final class PrintAction implements Action {
    @Override
    public void execute() {
        System.out.println("done");
    }
}
```

An implementing class must keep `public`; writing `protected` or package-private will reduce visibility and be rejected by the compiler. An interface can have `default`, `static`, or `private` methods **with a body**, but these forms do not create a package-private abstract method.

## 6. Choosing a modifier by purpose

- Use `public abstract` when the behavior is part of the API that client code needs to call.
- Use `protected abstract` when you want subclasses to extend the behavior without exposing the call to all callers.
- Use package-private abstract when the implementation is controlled within the same package and external subclasses do not need to fulfill the hook themselves.
- Before changing visibility to fix a compiler error, determine who needs to call the method and the package of the implementing class. `protected` allows overriding across packages but does not turn the method into a public API for every object.

## 7. Common errors and self-check

| Symptom | Cause to check |
|---|---|
| `attempting to assign weaker access privileges` | The override uses narrower visibility than the original contract |
| `does not override abstract method` | Wrong signature, not fully implemented, or a package-private method is in another package |
| Cannot call `protected` from external code | The caller does not satisfy `protected` access rules |
| Implementing an interface reports weaker visibility | Forgetting that an abstract method in an interface is public |

1. What access level is `abstract void save();` in a class? **Package-private.**
2. Can a subclass in another package override `protected abstract void save();` with `public void save()`? **Yes.**
3. Is `void save();` in an interface package-private? **No, it is implicitly public abstract.**
4. Has a subclass in another package declaring the same signature as a package-private abstract method fulfilled the contract? **No; that is not a valid override.**
